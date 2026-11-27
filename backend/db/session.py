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
# I consulenti di cui questo processo ha gia' visto la riga: la si crea una
# volta sola, alla prima sessione di un account nuovo.
_known_consultants: set[str] = set()


def canonical_engine() -> Engine:
    global _engine
    if _engine is None:
        if not settings.canonical_database_url:
            raise RuntimeError(
                "canonical_database_url non configurata: serve il DSN del ruolo "
                "delir_app (postgresql+psycopg://delir_app:...@host:port/delir)."
            )
        # Pool contenuto: un solo processo app, e il connection budget del
        # Postgres self-hosted va diviso con l'engine operativo (local_store,
        # 5+5), Mem0 e il checkpointer LangGraph. Web + graph_worker +
        # ingest_worker aprono tutti sessioni canonical.
        _engine = create_engine(
            settings.canonical_database_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=5,
            pool_recycle=1800,
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

    # difensivo: "None" / "null" / "" letterali -> nessun cliente, cosi'
    # app_client_id()::uuid non esplode su una stringa non-uuid.
    client_value = str(client_id).strip() if client_id else ""
    if client_value.lower() in {"none", "null"}:
        client_value = ""

    session = _factory()()
    try:
        session.execute(
            text("SELECT set_config('app.current_consultant_id', :v, true)"),
            {"v": str(consultant_id)},
        )
        session.execute(
            text("SELECT set_config('app.current_client_id', :v, true)"),
            {"v": client_value},
        )
        _ensure_consultant(session, str(consultant_id))
        yield session
        session.commit()
        # Dopo il commit: se la transazione si annulla, la riga non c'e'.
        _known_consultants.add(str(consultant_id))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _ensure_consultant(session: Session, consultant_id: str) -> None:
    """La riga `consultant` di un account personale, se ancora non c'e'.

    Ogni scope canonical (cliente, progetto, memoria, coda) punta al suo
    consulente: la prima volta che una persona lavora la riga deve gia' esserci.
    La policy `consultant_self` (0005) lascia inserire solo la propria riga.
    L'email e' un segnaposto unico: l'identita' vera sta in Supabase, non qui.
    Il consulente di default lo semina la migrazione 0007.
    """
    if consultant_id in _known_consultants:
        return
    from backend.security import tenant_id_for_consultant

    try:
        workspace_id = tenant_id_for_consultant(consultant_id)
    except ValueError:  # non e' un UUID: la sessione fallira' comunque sul cast
        return
    if workspace_id is not None:
        session.execute(
            text(
                "INSERT INTO consultant (id, email, display_name, workspace_id) "
                "VALUES (CAST(:id AS uuid), :email, 'Account', :ws) "
                "ON CONFLICT (id) DO NOTHING"
            ),
            {"id": consultant_id, "email": f"{consultant_id}@account.delir", "ws": workspace_id},
        )
