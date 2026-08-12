import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


DATA_DIR = Path("data")
CHAT_HISTORY_DB = DATA_DIR / "chat_history.db"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def chat_connection():
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(CHAT_HISTORY_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")

    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_chat_history_db() -> None:
    with chat_connection() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_sessions (
                thread_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                model_name TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (thread_id) REFERENCES chat_sessions(thread_id)
                    ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_chat_messages_thread_id_id
            ON chat_messages(thread_id, id)
            """
        )


def create_chat_session(thread_id: str, model_name: str | None, title: str = "Nuova chat") -> dict:
    now = utc_now()

    with chat_connection() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO chat_sessions (
                thread_id,
                title,
                model_name,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (thread_id, title, model_name, now, now),
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
    with chat_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                s.thread_id,
                s.title,
                s.model_name,
                s.created_at,
                s.updated_at,
                COUNT(m.id) AS message_count
            FROM chat_sessions s
            LEFT JOIN chat_messages m ON m.thread_id = s.thread_id
            GROUP BY s.thread_id
            ORDER BY s.updated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [dict(row) for row in rows]


def get_chat_session(thread_id: str) -> dict | None:
    with chat_connection() as conn:
        session = conn.execute(
            """
            SELECT thread_id, title, model_name, created_at, updated_at
            FROM chat_sessions
            WHERE thread_id = ?
            """,
            (thread_id,),
        ).fetchone()

        if session is None:
            return None

        messages = conn.execute(
            """
            SELECT id, role, content, created_at
            FROM chat_messages
            WHERE thread_id = ?
            ORDER BY id ASC
            """,
            (thread_id,),
        ).fetchall()

    result = dict(session)
    result["messages"] = [dict(message) for message in messages]
    return result


def append_chat_message(thread_id: str, role: str, content: str, model_name: str | None = None) -> None:
    now = utc_now()
    normalized_content = content.strip()

    if not normalized_content:
        return

    with chat_connection() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO chat_sessions (
                thread_id,
                title,
                model_name,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (thread_id, title_from_message(normalized_content), model_name, now, now),
        )

        conn.execute(
            """
            INSERT INTO chat_messages (thread_id, role, content, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (thread_id, role, normalized_content, now),
        )

        if role == "user":
            conn.execute(
                """
                UPDATE chat_sessions
                SET title = CASE
                        WHEN title = 'Nuova chat' THEN ?
                        ELSE title
                    END,
                    model_name = COALESCE(model_name, ?),
                    updated_at = ?
                WHERE thread_id = ?
                """,
                (title_from_message(normalized_content), model_name, now, thread_id),
            )
        else:
            conn.execute(
                """
                UPDATE chat_sessions
                SET updated_at = ?
                WHERE thread_id = ?
                """,
                (now, thread_id),
            )


def title_from_message(message: str) -> str:
    compact = " ".join(message.split())

    if not compact:
        return "Nuova chat"

    return compact[:34] + "..." if len(compact) > 34 else compact


def delete_chat_session(thread_id: str) -> None:
    with chat_connection() as conn:
        conn.execute("DELETE FROM chat_messages WHERE thread_id = ?", (thread_id,))
        conn.execute("DELETE FROM chat_sessions WHERE thread_id = ?", (thread_id,))


def delete_all_chat_sessions() -> None:
    with chat_connection() as conn:
        conn.execute("DELETE FROM chat_messages")
        conn.execute("DELETE FROM chat_sessions")


init_chat_history_db()
