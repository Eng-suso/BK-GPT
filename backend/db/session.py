"""Engine e sessione scoped per il Postgres canonical.

`canonical_session(consultant_id, client_id)` e' l'UNICO modo previsto per
toccare il DB canonical dall'app: apre una transazione e vi imposta il contesto
RLS con `set_config(..., is_local => true)`, cosi' le policy di INV-6 filtrano
ogni query. Il gateway di retrieval (INV-9) e i toolset di memoria lo useranno.
"""

from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.settings import settings

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def canonical_engine() -> Engine:
    global _engine
    if _engine is None:
        if not settings.canonical_database_url:
            raise RuntimeError(
                "canonical_database_url non configurata: serve il DSN del ruolo "
                "delir_app (postgresql+psycopg://delir_app:...@host:port/delir)."
            )
        _engine = create_engine(
            settings.canonical_database_url,
            pool_pre_ping=True,
            future=True,
        )
    return _engine


def _factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=canonical_engine(),
            autoflush=False,
            expire_on_commit=False,
            future=True,
        )
    return _session_factory


@contextmanager
def canonical_session(
    consultant_id: str,
    client_id: str | None = None,
) -> Iterator[Session]:
    """Transazione sul DB canonical con il contesto RLS impostato.

    consultant_id: obbligatorio, identifica il consulente proprietario.
    client_id: None per un contesto solo-consultant (es. metodo L2); altrimenti
        limita la visibilita' alle righe di quel cliente + a quelle
        consultant-scoped (client_id IS NULL).
    """
    if not consultant_id:
        raise ValueError("consultant_id obbligatorio per canonical_session")

    session = _factory()()
    try:
        session.execute(
            text("SELECT set_config('app.current_consultant_id', :v, true)"),
            {"v": str(consultant_id)},
        )
        session.execute(
            text("SELECT set_config('app.current_client_id', :v, true)"),
            {"v": str(client_id) if client_id else ""},
        )
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
