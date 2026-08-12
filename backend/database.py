from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import ForeignKey, String, Text, create_engine, func, select
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


def create_chat_session(thread_id: str, model_name: str | None, title: str = "Nuova chat") -> dict:
    now = utc_now()

    with chat_connection() as session:
        if session.get(ChatSession, thread_id) is None:
            session.add(
                ChatSession(
                    thread_id=thread_id,
                    title=title,
                    model_name=model_name,
                    created_at=now,
                    updated_at=now,
                )
            )

    return get_chat_session(thread_id) or {
        "thread_id": thread_id,
        "title": title,
        "model_name": model_name,
        "created_at": now,
        "updated_at": now,
        "messages": [],
    }


def list_chat_sessions(limit: int = 50) -> list[dict]:
    statement = (
        select(
            ChatSession.thread_id,
            ChatSession.title,
            ChatSession.model_name,
            ChatSession.created_at,
            ChatSession.updated_at,
            func.count(ChatMessage.id).label("message_count"),
        )
        .outerjoin(ChatMessage, ChatMessage.thread_id == ChatSession.thread_id)
        .group_by(ChatSession.thread_id)
        .order_by(ChatSession.updated_at.desc())
        .limit(limit)
    )

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
            "created_at": chat_session.created_at,
            "updated_at": chat_session.updated_at,
            "messages": [message_to_dict(message) for message in messages],
        }


def append_chat_message(thread_id: str, role: str, content: str, model_name: str | None = None) -> None:
    now = utc_now()
    normalized_content = content.strip()

    if not normalized_content:
        return

    with chat_connection() as session:
        chat_session = session.get(ChatSession, thread_id)

        if chat_session is None:
            chat_session = ChatSession(
                thread_id=thread_id,
                title=title_from_message(normalized_content),
                model_name=model_name,
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


init_chat_history_db()
