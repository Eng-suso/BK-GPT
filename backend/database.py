from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, String, Text, and_, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from backend.local_store import local_engine
from backend.security import get_current_tenant_id


class Base(DeclarativeBase):
    pass


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    thread_id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="local", index=True)
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
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="local", index=True)
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
    return local_engine()


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
    tenant_id = get_current_tenant_id()
    scope_fields = normalize_scope_fields(
        scope_type=scope_type,
        project_id=project_id,
        process_id=process_id,
        bpmn_model_id=bpmn_model_id,
        scope_key=scope_key,
    )

    with chat_connection() as session:
        existing_session = session.get(ChatSession, thread_id)
        if existing_session is not None and existing_session.tenant_id != tenant_id:
            raise ValueError("Sessione non disponibile per il tenant corrente.")

        if existing_session is None:
            session.add(
                ChatSession(
                    thread_id=thread_id,
                    tenant_id=tenant_id,
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
    tenant_id = get_current_tenant_id()
    statement = (
        select(
            ChatSession.thread_id,
            ChatSession.tenant_id,
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
    statement = statement.where(ChatSession.tenant_id == tenant_id)

    if scope_key:
        statement = statement.where(ChatSession.scope_key == scope_key)

    with chat_connection() as session:
        rows = session.execute(statement).mappings().all()

    return [dict(row) for row in rows]


# Quanto testo mostrare intorno alla parola trovata, da un lato e dall'altro.
SEARCH_SNIPPET_RADIUS = 90
# Le parole oltre la quinta non restringono piu' niente di utile e allungano solo
# la query: una ricerca e' un modo per ritrovare una conversazione, non una
# interrogazione full-text.
SEARCH_MAX_TERMS = 5


def _like_escape(value: str) -> str:
    """Rende letterali i caratteri che LIKE interpreta.

    Senza, chi cerca `100%` chiede "qualunque cosa dopo 100" e chi cerca
    `client_id` trova anche `clientXid`.
    """
    for char in ("\\", "%", "_"):
        value = value.replace(char, f"\\{char}")
    return value


def search_terms(query: str) -> list[str]:
    """Le parole della ricerca, normalizzate, al piu' `SEARCH_MAX_TERMS`."""
    return [term.lower() for term in query.split()][:SEARCH_MAX_TERMS]


def _snippet(content: str, terms: list[str]) -> str:
    """Il pezzo di messaggio intorno alla prima parola trovata.

    Un risultato senza contesto non si distingue dagli altri: il titolo di una
    chat e' quasi sempre la prima domanda, e dieci conversazioni sullo stesso
    processo hanno titoli quasi identici. Cio' che dice quale riaprire e' la
    riga in cui la parola compare.
    """
    compact = " ".join(content.split())
    lowered = compact.lower()
    position = min(
        (found for found in (lowered.find(term) for term in terms) if found >= 0),
        default=-1,
    )
    if position < 0:
        return compact[: SEARCH_SNIPPET_RADIUS * 2].rstrip()

    start = max(0, position - SEARCH_SNIPPET_RADIUS)
    end = min(len(compact), position + SEARCH_SNIPPET_RADIUS)
    return (
        ("..." if start > 0 else "")
        + compact[start:end].strip()
        + ("..." if end < len(compact) else "")
    )


def search_chat_sessions(
    query: str,
    *,
    scope_key: str | None = None,
    limit: int = 30,
    message_scan_limit: int = 400,
) -> list[dict]:
    """Cerca fra le conversazioni del tenant, per titolo e per testo scambiato.

    Tutte le parole devono comparire nello stesso messaggio (o nello stesso
    titolo): cercare "ordine fornitore" deve trovare "l'ordine al fornitore",
    che una sottostringa secca non troverebbe, senza pero' restituire ogni
    conversazione che nomina un ordine qualunque.

    Args:
        query: Il testo cercato, non affidabile; vuoto significa nessun risultato.
        scope_key: Limita la ricerca alla superficie da cui e' partita (il
            processo aperto, il progetto, il consulente). ``None`` cerca ovunque.
        limit: Quante conversazioni restituire al massimo.
        message_scan_limit: Quanti messaggi corrispondenti leggere prima di
            fermarsi. Il conteggio delle occorrenze si ferma li' con loro: e' un
            "quanto ne parla", non un totale contrattuale.

    Returns:
        Le conversazioni trovate, dalla piu' recente, ognuna col riassunto di
        lista piu' `snippet`, `snippet_role` e `match_count`.
    """
    terms = search_terms(query)
    if not terms:
        return []

    tenant_id = get_current_tenant_id()
    patterns = [f"%{_like_escape(term)}%" for term in terms]

    def _scoped(statement):
        statement = statement.where(ChatSession.tenant_id == tenant_id)
        return statement.where(ChatSession.scope_key == scope_key) if scope_key else statement

    with chat_connection() as session:
        message_statement = _scoped(
            select(ChatMessage.thread_id, ChatMessage.role, ChatMessage.content)
            .join(ChatSession, ChatSession.thread_id == ChatMessage.thread_id)
            .where(ChatMessage.tenant_id == tenant_id)
            .where(
                and_(
                    *(
                        func.lower(ChatMessage.content).like(pattern, escape="\\")
                        for pattern in patterns
                    )
                )
            )
            .order_by(ChatSession.updated_at.desc(), ChatMessage.id.asc())
            .limit(message_scan_limit)
        )

        hits: dict[str, dict] = {}
        for thread_id, role, content in session.execute(message_statement).all():
            hit = hits.setdefault(
                thread_id, {"match_count": 0, "snippet": "", "snippet_role": None}
            )
            hit["match_count"] += 1
            if not hit["snippet"]:
                hit["snippet"] = _snippet(content, terms)
                hit["snippet_role"] = role

        # Una conversazione il cui titolo corrisponde e' un risultato anche se il
        # testo non ripete quelle parole: e' il caso di chi ha rinominato la chat
        # per ritrovarla.
        title_statement = _scoped(
            select(ChatSession.thread_id).where(
                and_(
                    *(
                        func.lower(ChatSession.title).like(pattern, escape="\\")
                        for pattern in patterns
                    )
                )
            )
        )
        for (thread_id,) in session.execute(title_statement).all():
            hits.setdefault(thread_id, {"match_count": 0, "snippet": "", "snippet_role": None})

        if not hits:
            return []

        summary_statement = (
            select(
                ChatSession.thread_id,
                ChatSession.tenant_id,
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
            .where(ChatSession.thread_id.in_(list(hits)))
            .where(ChatSession.tenant_id == tenant_id)
            .group_by(ChatSession.thread_id)
            .order_by(ChatSession.updated_at.desc())
            .limit(limit)
        )
        rows = session.execute(summary_statement).mappings().all()

    return [{**dict(row), **hits[row["thread_id"]]} for row in rows]


def get_chat_session(thread_id: str) -> dict | None:
    tenant_id = get_current_tenant_id()
    with chat_connection() as db_session:
        chat_session = db_session.get(ChatSession, thread_id)

        if chat_session is None or chat_session.tenant_id != tenant_id:
            return None

        messages = db_session.execute(
            select(ChatMessage)
            .where(ChatMessage.thread_id == thread_id)
            .where(ChatMessage.tenant_id == tenant_id)
            .order_by(ChatMessage.id.asc())
        ).scalars().all()

        return {
            "thread_id": chat_session.thread_id,
            "tenant_id": chat_session.tenant_id,
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
    tenant_id = get_current_tenant_id()
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

        if chat_session is not None and chat_session.tenant_id != tenant_id:
            raise ValueError("Sessione non disponibile per il tenant corrente.")

        if chat_session is None:
            chat_session = ChatSession(
                thread_id=thread_id,
                tenant_id=tenant_id,
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
                tenant_id=tenant_id,
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
    tenant_id = get_current_tenant_id()
    with chat_connection() as session:
        chat_session = session.get(ChatSession, thread_id)

        if chat_session is not None and chat_session.tenant_id == tenant_id:
            session.delete(chat_session)


def delete_all_chat_sessions() -> None:
    tenant_id = get_current_tenant_id()
    with chat_connection() as session:
        for chat_session in session.execute(
            select(ChatSession).where(ChatSession.tenant_id == tenant_id)
        ).scalars():
            session.delete(chat_session)


def delete_chat_sessions_by_scope(scope_key: str) -> None:
    tenant_id = get_current_tenant_id()
    with chat_connection() as session:
        statement = (
            select(ChatSession)
            .where(ChatSession.scope_key == scope_key)
            .where(ChatSession.tenant_id == tenant_id)
        )

        for chat_session in session.execute(statement).scalars():
            session.delete(chat_session)
