from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import ForeignKey, String, Text, create_engine, func, inspect, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


DATA_DIR = Path("data")
CHAT_HISTORY_DB = DATA_DIR / "chat_history.db"
CHAT_HISTORY_DB_URL = f"sqlite:///{CHAT_HISTORY_DB.as_posix()}"


class Base(DeclarativeBase):
    pass


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    thread_id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    model_name: Mapped[str | None] = mapped_column(String)
    scope_type: Mapped[str | None] = mapped_column(String, index=True)
    project_id: Mapped[str | None] = mapped_column(String, index=True)
    process_id: Mapped[str | None] = mapped_column(String, index=True)
    bpmn_model_id: Mapped[str | None] = mapped_column(String, index=True)
    scope_key: Mapped[str | None] = mapped_column(String, index=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)

    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.id",
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    thread_id: Mapped[str] = mapped_column(
        ForeignKey("chat_sessions.thread_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)

    session: Mapped[ChatSession] = relationship(back_populates="messages")


def build_engine():
    DATA_DIR.mkdir(exist_ok=True)
    return create_engine(
        CHAT_HISTORY_DB_URL,
        connect_args={"check_same_thread": False},
    )


engine = build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def chat_connection():
    session = SessionLocal()

    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_chat_history_db() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    Base.metadata.create_all(engine)
    ensure_chat_session_scope_columns()


def ensure_chat_session_scope_columns() -> None:
    inspector = inspect(engine)
    existing_columns = {column["name"] for column in inspector.get_columns("chat_sessions")}
    scope_columns = {
        "scope_type": "VARCHAR",
        "project_id": "VARCHAR",
        "process_id": "VARCHAR",
        "bpmn_model_id": "VARCHAR",
        "scope_key": "VARCHAR",
    }

    with engine.begin() as connection:
        for column_name, column_type in scope_columns.items():
            if column_name not in existing_columns:
                connection.execute(text(f"ALTER TABLE chat_sessions ADD COLUMN {column_name} {column_type}"))

        connection.execute(
            text(
                "UPDATE chat_sessions "
                "SET scope_type = 'consultant', scope_key = 'consultant' "
                "WHERE scope_key IS NULL"
            )
        )


def normalize_scope_fields(
    scope_type: str | None = None,
    project_id: str | None = None,
    process_id: str | None = None,
    bpmn_model_id: str | None = None,
    scope_key: str | None = None,
) -> dict:
    normalized_scope_type = scope_type or "consultant"
    normalized_scope_key = scope_key or "consultant"

    return {
        "scope_type": normalized_scope_type,
        "project_id": project_id,
        "process_id": process_id,
        "bpmn_model_id": bpmn_model_id,
        "scope_key": normalized_scope_key,
    }


def create_chat_session(
    thread_id: str,
    model_name: str | None,
    title: str = "Nuova chat",
    scope_type: str | None = None,
    project_id: str | None = None,
    process_id: str | None = None,
    bpmn_model_id: str | None = None,
    scope_key: str | None = None,
) -> dict:
    now = utc_now()
    scope_fields = normalize_scope_fields(
        scope_type=scope_type,
        project_id=project_id,
        process_id=process_id,
        bpmn_model_id=bpmn_model_id,
        scope_key=scope_key,
    )

    with chat_connection() as session:
        if session.get(ChatSession, thread_id) is None:
            session.add(
                ChatSession(
                    thread_id=thread_id,
                    title=title,
                    model_name=model_name,
                    **scope_fields,
                    created_at=now,
                    updated_at=now,
                )
            )

    return get_chat_session(thread_id) or {
        "thread_id": thread_id,
        "title": title,
        "model_name": model_name,
        **scope_fields,
        "created_at": now,
        "updated_at": now,
        "messages": [],
    }


def list_chat_sessions(limit: int = 50, scope_key: str | None = None) -> list[dict]:
    statement = (
        select(
            ChatSession.thread_id,
            ChatSession.title,
            ChatSession.model_name,
            ChatSession.scope_type,
            ChatSession.project_id,
            ChatSession.process_id,
            ChatSession.bpmn_model_id,
            ChatSession.scope_key,
            ChatSession.created_at,
            ChatSession.updated_at,
            func.count(ChatMessage.id).label("message_count"),
        )
        .outerjoin(ChatMessage, ChatMessage.thread_id == ChatSession.thread_id)
        .group_by(ChatSession.thread_id)
        .order_by(ChatSession.updated_at.desc())
        .limit(limit)
    )

    if scope_key:
        statement = statement.where(ChatSession.scope_key == scope_key)

    with chat_connection() as session:
        rows = session.execute(statement).mappings().all()

    return [dict(row) for row in rows]


def get_chat_session(thread_id: str) -> dict | None:
    with chat_connection() as db_session:
        chat_session = db_session.get(ChatSession, thread_id)

        if chat_session is None:
            return None

        messages = db_session.execute(
            select(ChatMessage)
            .where(ChatMessage.thread_id == thread_id)
            .order_by(ChatMessage.id.asc())
        ).scalars().all()

        return {
            "thread_id": chat_session.thread_id,
            "title": chat_session.title,
            "model_name": chat_session.model_name,
            "scope_type": chat_session.scope_type or "consultant",
            "project_id": chat_session.project_id,
            "process_id": chat_session.process_id,
            "bpmn_model_id": chat_session.bpmn_model_id,
            "scope_key": chat_session.scope_key or "consultant",
            "created_at": chat_session.created_at,
            "updated_at": chat_session.updated_at,
            "messages": [message_to_dict(message) for message in messages],
        }


def append_chat_message(
    thread_id: str,
    role: str,
    content: str,
    model_name: str | None = None,
    scope_type: str | None = None,
    project_id: str | None = None,
    process_id: str | None = None,
    bpmn_model_id: str | None = None,
    scope_key: str | None = None,
) -> None:
    now = utc_now()
    normalized_content = content.strip()
    scope_fields = normalize_scope_fields(
        scope_type=scope_type,
        project_id=project_id,
        process_id=process_id,
        bpmn_model_id=bpmn_model_id,
        scope_key=scope_key,
    )

    if not normalized_content:
        return

    with chat_connection() as session:
        chat_session = session.get(ChatSession, thread_id)

        if chat_session is None:
            chat_session = ChatSession(
                thread_id=thread_id,
                title=title_from_message(normalized_content),
                model_name=model_name,
                **scope_fields,
                created_at=now,
                updated_at=now,
            )
            session.add(chat_session)

        session.add(
            ChatMessage(
                thread_id=thread_id,
                role=role,
                content=normalized_content,
                created_at=now,
            )
        )

        if role == "user":
            if chat_session.title == "Nuova chat":
                chat_session.title = title_from_message(normalized_content)

            if chat_session.model_name is None:
                chat_session.model_name = model_name

            chat_session.updated_at = now
        else:
            chat_session.updated_at = now


def message_to_dict(message: ChatMessage) -> dict:
    return {
        "id": message.id,
        "role": message.role,
        "content": message.content,
        "created_at": message.created_at,
    }


def title_from_message(message: str) -> str:
    compact = " ".join(message.split())

    if not compact:
        return "Nuova chat"

    return compact[:34] + "..." if len(compact) > 34 else compact


def delete_chat_session(thread_id: str) -> None:
    with chat_connection() as session:
        chat_session = session.get(ChatSession, thread_id)

        if chat_session is not None:
            session.delete(chat_session)


def delete_all_chat_sessions() -> None:
    with chat_connection() as session:
        for chat_session in session.execute(select(ChatSession)).scalars():
            session.delete(chat_session)


def delete_chat_sessions_by_scope(scope_key: str) -> None:
    with chat_connection() as session:
        statement = select(ChatSession).where(ChatSession.scope_key == scope_key)

        for chat_session in session.execute(statement).scalars():
            session.delete(chat_session)


init_chat_history_db()
