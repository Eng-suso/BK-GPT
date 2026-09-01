import hashlib
import json
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import ForeignKey, Index, String, Text, create_engine, func, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from backend.memory.models import EpisodeMemory, episode_memory_to_mem0_content
from backend.memory.semantic.semantic_store import (
    add_mem0_memory_with_id,
    mirror_episodic_to_canonical,
    search_consultant_memory,
)


DATA_DIR = Path("data") / "episodic"
SOURCES_DIR = DATA_DIR / "sources"
EPISODIC_MEMORY_DB = DATA_DIR / "episodic_memory.db"
EPISODIC_MEMORY_DB_URL = f"sqlite:///{EPISODIC_MEMORY_DB.as_posix()}"


class Base(DeclarativeBase):
    pass


class Episode(Base):
    __tablename__ = "episodes"
    __table_args__ = (
        Index("idx_episodes_type_project_date", "episode_type", "project", "occurred_at"),
    )

    episode_id: Mapped[str] = mapped_column(String, primary_key=True)
    episode_type: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    occurred_at: Mapped[str | None] = mapped_column(String)
    participants: Mapped[str] = mapped_column(Text, nullable=False)
    project: Mapped[str | None] = mapped_column(String)
    summary: Mapped[str | None] = mapped_column(Text)
    insights: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    archived_at: Mapped[str | None] = mapped_column(String)
    archive_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)

    sources: Mapped[list["EpisodeSource"]] = relationship(
        back_populates="episode",
        cascade="all, delete-orphan",
    )


class EpisodeSource(Base):
    __tablename__ = "sources"

    source_id: Mapped[str] = mapped_column(String, primary_key=True)
    episode_id: Mapped[str] = mapped_column(
        ForeignKey("episodes.episode_id", ondelete="CASCADE"),
        nullable=False,
    )
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    origin: Mapped[str] = mapped_column(String, nullable=False)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)

    episode: Mapped[Episode] = relationship(back_populates="sources")


def build_engine():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return create_engine(
        EPISODIC_MEMORY_DB_URL,
        connect_args={"check_same_thread": False},
    )


engine = build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def episodic_connection():
    session = SessionLocal()

    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_episodic_memory_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    ensure_episodic_lifecycle_columns()


def ensure_episodic_lifecycle_columns() -> None:
    with engine.begin() as connection:
        columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(episodes)")).fetchall()
        }
        if "status" not in columns:
            connection.execute(
                text("ALTER TABLE episodes ADD COLUMN status VARCHAR NOT NULL DEFAULT 'active'")
            )
        if "archived_at" not in columns:
            connection.execute(text("ALTER TABLE episodes ADD COLUMN archived_at VARCHAR"))
        if "archive_reason" not in columns:
            connection.execute(text("ALTER TABLE episodes ADD COLUMN archive_reason TEXT"))


def normalize_list(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []

    if isinstance(value, list):
        return [item.strip() for item in value if item.strip()]

    return [item.strip() for item in value.split(",") if item.strip()]


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return slug[:60] or "episode"


def source_directory(episode_type: str) -> Path:
    directory = SOURCES_DIR / f"{slugify(episode_type)}s"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def save_raw_source(
    episode_id: str,
    episode_type: str,
    title: str,
    raw_content: str,
    occurred_at: str | None,
) -> dict:
    source_id = str(uuid4())
    date_prefix = (occurred_at or utc_now()).split("T")[0]
    filename = f"{date_prefix}_{slugify(title)}_{source_id[:8]}.md"
    path = source_directory(episode_type) / filename
    normalized_content = raw_content.strip()

    path.write_text(normalized_content, encoding="utf-8")

    return {
        "source_id": source_id,
        "episode_id": episode_id,
        "source_type": episode_type,
        "title": title,
        "path": str(path),
        "origin": "chat",
        "content_hash": hashlib.sha256(
            normalized_content.encode("utf-8")
        ).hexdigest(),
        "created_at": utc_now(),
    }


def build_mem0_episode_content(episode: dict, source: dict) -> str:
    memory = EpisodeMemory(
        episode_type=episode["episode_type"],
        title=episode["title"],
        raw_content="indexed separately in local source custody",
        summary=episode.get("summary") or "",
        insights=json.loads(episode["insights"] or "[]"),
        participants=json.loads(episode["participants"] or "[]"),
        project=episode.get("project"),
        tags=json.loads(episode["tags"] or "[]"),
        occurred_at=episode.get("occurred_at"),
    )
    return episode_memory_to_mem0_content(
        memory=memory,
        episode_id=episode["episode_id"],
        source_id=source["source_id"],
        source_path=source["path"],
    )


def save_structured_episode_memory(memory: EpisodeMemory) -> str:
    return save_episode_memory(
        episode_type=memory.episode_type,
        title=memory.title,
        raw_content=memory.raw_content,
        summary=memory.summary,
        insights=memory.insights,
        participants=memory.participants,
        project=memory.project,
        tags=memory.tags,
        occurred_at=memory.occurred_at,
    )


def save_episode_memory(
    episode_type: str,
    title: str,
    raw_content: str,
    summary: str = "",
    insights: str | list[str] | None = None,
    participants: str | list[str] | None = None,
    project: str | None = None,
    tags: str | list[str] | None = None,
    occurred_at: str | None = None,
) -> str:
    normalized_raw_content = raw_content.strip()

    if not normalized_raw_content:
        return "Non posso salvare l'episodio: raw_content mancante."

    episode_id = str(uuid4())
    now = utc_now()
    episode = {
        "episode_id": episode_id,
        "episode_type": episode_type.strip() or "note",
        "title": title.strip() or "Episodio senza titolo",
        "occurred_at": occurred_at.strip() if occurred_at else None,
        "participants": json.dumps(normalize_list(participants), ensure_ascii=False),
        "project": project.strip() if project else None,
        "summary": summary.strip(),
        "insights": json.dumps(normalize_list(insights), ensure_ascii=False),
        "tags": json.dumps(normalize_list(tags), ensure_ascii=False),
        "status": "active",
        "archived_at": None,
        "archive_reason": None,
        "created_at": now,
        "updated_at": now,
    }
    source = save_raw_source(
        episode_id=episode_id,
        episode_type=episode["episode_type"],
        title=episode["title"],
        raw_content=normalized_raw_content,
        occurred_at=episode["occurred_at"],
    )
    episode["source_id"] = source["source_id"]

    with episodic_connection() as session:
        session.add(
            Episode(
                episode_id=episode["episode_id"],
                episode_type=episode["episode_type"],
                title=episode["title"],
                occurred_at=episode["occurred_at"],
                participants=episode["participants"],
                project=episode["project"],
                summary=episode["summary"],
                insights=episode["insights"],
                tags=episode["tags"],
                source_id=episode["source_id"],
                status=episode["status"],
                archived_at=episode["archived_at"],
                archive_reason=episode["archive_reason"],
                created_at=episode["created_at"],
                updated_at=episode["updated_at"],
            )
        )
        session.add(
            EpisodeSource(
                source_id=source["source_id"],
                episode_id=source["episode_id"],
                source_type=source["source_type"],
                title=source["title"],
                path=source["path"],
                origin=source["origin"],
                content_hash=source["content_hash"],
                created_at=source["created_at"],
            )
        )

    mem0_result, mem0_id = add_mem0_memory_with_id(build_mem0_episode_content(episode, source))
    mirror_episodic_to_canonical(
        episode_type=episode["episode_type"],
        title=episode["title"],
        summary=episode["summary"] or episode["title"],
        mem0_id=mem0_id,
    )

    return (
        f"Episodio salvato: {episode['title']} "
        f"[episode_id: {episode_id}] [source_id: {source['source_id']}]. "
        f"{mem0_result}"
    )


def local_episode_matches(
    query: str,
    episode_type: str | None = None,
    project: str | None = None,
    limit: int = 5,
    include_archived: bool = False,
) -> list[dict]:
    statement = (
        select(Episode, EpisodeSource)
        .join(EpisodeSource, EpisodeSource.source_id == Episode.source_id, isouter=True)
        .order_by(func.coalesce(Episode.occurred_at, Episode.created_at).desc())
        .limit(max(limit * 10, 20))
    )

    if episode_type:
        statement = statement.where(Episode.episode_type == episode_type)

    if project:
        statement = statement.where(Episode.project == project)

    if not include_archived:
        statement = statement.where(Episode.status == "active")

    matches = []

    with episodic_connection() as session:
        rows = session.execute(statement).all()

    for episode, source in rows:
        match = episode_to_dict(episode, source)

        if episode_matches_query(match, query):
            matches.append(match)

        if len(matches) >= limit:
            break

    return matches


def episode_to_dict(episode: Episode, source: EpisodeSource | None) -> dict:
    return {
        "episode_id": episode.episode_id,
        "episode_type": episode.episode_type,
        "title": episode.title,
        "occurred_at": episode.occurred_at,
        "participants": episode.participants,
        "project": episode.project,
        "summary": episode.summary,
        "insights": episode.insights,
        "tags": episode.tags,
        "status": episode.status,
        "archived_at": episode.archived_at,
        "archive_reason": episode.archive_reason,
        "source_id": source.source_id if source else episode.source_id,
        "path": source.path if source else "",
        "content_hash": source.content_hash if source else "",
        "created_at": episode.created_at,
        "updated_at": episode.updated_at,
    }


def read_source_text(path: str | None) -> str:
    if not path:
        return ""

    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return ""


def episode_matches_query(match: dict, query: str) -> bool:
    terms = [term.strip().lower() for term in query.split() if term.strip()]

    if not terms:
        return True

    source_text = read_source_text(match.get("path"))
    haystack = " ".join(
        [
            match.get("title") or "",
            match.get("episode_type") or "",
            match.get("project") or "",
            match.get("summary") or "",
            match.get("insights") or "",
            match.get("tags") or "",
            match.get("participants") or "",
            source_text,
        ]
    ).lower()

    return all(term in haystack for term in terms)


def format_local_episode_matches(matches: list[dict]) -> str:
    if not matches:
        return "REGISTRO EPISODICO LOCALE: nessun episodio rilevante trovato."

    formatted = []

    for match in matches:
        insights = json.loads(match["insights"] or "[]")
        tags = json.loads(match["tags"] or "[]")
        participants = json.loads(match["participants"] or "[]")
        formatted.append(
            " | ".join(
                [
                    f"[episode_id: {match['episode_id']}]",
                    f"[source_id: {match['source_id']}]",
                    f"type: {match['episode_type']}",
                    f"title: {match['title']}",
                    f"date: {match['occurred_at'] or 'unknown'}",
                    f"participants: {', '.join(participants) or 'unknown'}",
                    f"project: {match['project'] or 'none'}",
                    f"status: {match.get('status') or 'active'}",
                    f"tags: {', '.join(tags) or 'none'}",
                    f"summary: {match['summary'] or 'none'}",
                    f"insights: {'; '.join(insights) or 'none'}",
                    f"source_path: {match['path']}",
                ]
            )
        )

    return "REGISTRO EPISODICO LOCALE RECUPERATO.\n" + "\n".join(formatted)


def search_episode_memory(
    query: str,
    episode_type: str | None = None,
    project: str | None = None,
    limit: int = 5,
    include_archived: bool = False,
) -> str:
    category = f"episodic:{episode_type}" if episode_type else "episodic"
    mem0_result = search_consultant_memory(query=query, category=category)
    local_result = format_local_episode_matches(
        local_episode_matches(
            query=query,
            episode_type=episode_type,
            project=project,
            limit=limit,
            include_archived=include_archived,
        )
    )

    return (
        "MEMORIA EPISODICA RECUPERATA.\n"
        "Usa questi episodi come evidenza contestuale, mantenendo data, fonte e "
        "source_id quando servono. Non confonderli con preferenze stabili o "
        "profilo canonico.\n\n"
        f"{mem0_result}\n\n{local_result}"
    )


def save_interview_memory(
    title: str,
    raw_content: str,
    summary: str = "",
    insights: str | list[str] | None = None,
    participants: str | list[str] | None = None,
    project: str | None = None,
    tags: str | list[str] | None = None,
    occurred_at: str | None = None,
) -> str:
    return save_episode_memory(
        episode_type="interview",
        title=title,
        raw_content=raw_content,
        summary=summary,
        insights=insights,
        participants=participants,
        project=project,
        tags=tags,
        occurred_at=occurred_at,
    )


def search_interview_memory(
    query: str,
    project: str | None = None,
    limit: int = 5,
    include_archived: bool = False,
) -> str:
    return search_episode_memory(
        query=query,
        episode_type="interview",
        project=project,
        limit=limit,
        include_archived=include_archived,
    )


def _episode_statement(episode_id: str | None = None, source_id: str | None = None):
    statement = select(Episode, EpisodeSource).join(
        EpisodeSource,
        EpisodeSource.source_id == Episode.source_id,
        isouter=True,
    )
    if episode_id:
        return statement.where(Episode.episode_id == episode_id)
    if source_id:
        return statement.where(EpisodeSource.source_id == source_id)
    return statement.where(Episode.episode_id == "")


def get_episode_memory(
    episode_id: str | None = None,
    source_id: str | None = None,
    include_source_text: bool = False,
) -> dict | None:
    with episodic_connection() as session:
        row = session.execute(_episode_statement(episode_id, source_id)).first()

    if not row:
        return None

    episode, source = row
    result = episode_to_dict(episode, source)
    if include_source_text:
        result["source_text"] = read_source_text(result.get("path"))
    return result


def list_episode_memory(
    *,
    project: str | None = None,
    episode_type: str | None = None,
    query: str = "",
    status: str = "active",
    limit: int = 20,
) -> list[dict]:
    statement = (
        select(Episode, EpisodeSource)
        .join(EpisodeSource, EpisodeSource.source_id == Episode.source_id, isouter=True)
        .order_by(func.coalesce(Episode.occurred_at, Episode.created_at).desc())
        .limit(max(min(limit, 100), 1) * 3)
    )
    if project:
        statement = statement.where(Episode.project == project)
    if episode_type:
        statement = statement.where(Episode.episode_type == episode_type)
    if status != "any":
        statement = statement.where(Episode.status == status)

    with episodic_connection() as session:
        rows = session.execute(statement).all()

    matches = []
    for episode, source in rows:
        item = episode_to_dict(episode, source)
        if query and not episode_matches_query(item, query):
            continue
        matches.append(item)
        if len(matches) >= limit:
            break
    return matches


def update_episode_metadata(
    episode_id: str,
    *,
    title: str | None = None,
    summary: str | None = None,
    insights: list[str] | str | None = None,
    participants: list[str] | str | None = None,
    project: str | None = None,
    tags: list[str] | str | None = None,
    occurred_at: str | None = None,
) -> dict:
    normalized_episode_id = episode_id.strip()
    if not normalized_episode_id:
        return {"status": "error", "message": "episode_id mancante."}

    with episodic_connection() as session:
        episode = session.get(Episode, normalized_episode_id)
        if episode is None:
            return {"status": "not_found", "message": f"Episodio non trovato: {normalized_episode_id}"}

        if title is not None:
            episode.title = title.strip() or episode.title
        if summary is not None:
            episode.summary = summary.strip()
        if insights is not None:
            episode.insights = json.dumps(normalize_list(insights), ensure_ascii=False)
        if participants is not None:
            episode.participants = json.dumps(normalize_list(participants), ensure_ascii=False)
        if project is not None:
            episode.project = project.strip() or None
        if tags is not None:
            episode.tags = json.dumps(normalize_list(tags), ensure_ascii=False)
        if occurred_at is not None:
            episode.occurred_at = occurred_at.strip() or None
        episode.updated_at = utc_now()

    return {
        "status": "updated",
        "episode_id": normalized_episode_id,
        "message": f"Metadati episodio aggiornati: {normalized_episode_id}",
    }


def archive_episode_memory(episode_id: str, reason: str = "") -> dict:
    normalized_episode_id = episode_id.strip()
    if not normalized_episode_id:
        return {"status": "error", "message": "episode_id mancante."}

    now = utc_now()
    with episodic_connection() as session:
        episode = session.get(Episode, normalized_episode_id)
        if episode is None:
            return {"status": "not_found", "message": f"Episodio non trovato: {normalized_episode_id}"}
        episode.status = "archived"
        episode.archived_at = now
        episode.archive_reason = reason.strip()
        episode.updated_at = now

    return {
        "status": "archived",
        "episode_id": normalized_episode_id,
        "archived_at": now,
        "message": f"Episodio archiviato: {normalized_episode_id}",
    }


def restore_episode_memory(episode_id: str) -> dict:
    normalized_episode_id = episode_id.strip()
    if not normalized_episode_id:
        return {"status": "error", "message": "episode_id mancante."}

    now = utc_now()
    with episodic_connection() as session:
        episode = session.get(Episode, normalized_episode_id)
        if episode is None:
            return {"status": "not_found", "message": f"Episodio non trovato: {normalized_episode_id}"}
        episode.status = "active"
        episode.archived_at = None
        episode.archive_reason = None
        episode.updated_at = now

    return {
        "status": "restored",
        "episode_id": normalized_episode_id,
        "message": f"Episodio ripristinato: {normalized_episode_id}",
    }


def delete_episode_memory(
    episode_id: str,
    *,
    confirm_destructive_action: bool = False,
    delete_raw_source: bool = False,
) -> dict:
    normalized_episode_id = episode_id.strip()
    if not normalized_episode_id:
        return {"status": "error", "message": "episode_id mancante."}
    if not confirm_destructive_action:
        return {
            "status": "blocked",
            "episode_id": normalized_episode_id,
            "message": "Hard delete bloccato: serve confirm_destructive_action=True.",
        }

    source_paths = []
    with episodic_connection() as session:
        episode = session.get(Episode, normalized_episode_id)
        if episode is None:
            return {"status": "not_found", "message": f"Episodio non trovato: {normalized_episode_id}"}
        source_paths = [source.path for source in episode.sources if source.path]
        session.delete(episode)

    deleted_paths = []
    skipped_paths = []
    if delete_raw_source:
        source_root = SOURCES_DIR.resolve()
        for source_path in source_paths:
            path = Path(source_path)
            try:
                resolved = path.resolve()
                if not resolved.is_relative_to(source_root):
                    skipped_paths.append(str(path))
                    continue
                if resolved.exists():
                    resolved.unlink()
                    deleted_paths.append(str(resolved))
            except OSError:
                skipped_paths.append(str(path))

    return {
        "status": "deleted",
        "episode_id": normalized_episode_id,
        "deleted_raw_source_paths": deleted_paths,
        "skipped_raw_source_paths": skipped_paths,
        "message": f"Episodio eliminato: {normalized_episode_id}",
    }


init_episodic_memory_db()
