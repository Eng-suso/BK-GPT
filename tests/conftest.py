# conftest.py — shared pytest fixtures
import time
from collections.abc import Callable

import pytest

from backend.settings import settings


def _drain_until(drains: list[Callable[[], int]], check: Callable[[], bool], tries: int, delay: float) -> bool:
    for _ in range(tries):
        for drain in drains:
            drain()
        if check():
            return True
        time.sleep(delay)
    return False


@pytest.fixture()
def wait_projected():
    """drain di `graph_outbox` best-effort + retry finche' `check()` e' vero.

    Robusto a un worker in-process dell'app (uvicorn locale) che drena la stessa
    coda: in quel caso il `drain_once()` esplicito del test vede 0 righe ma la
    proiezione e' comunque avvenuta. Non asserire mai sul valore di ritorno di
    `drain_once()` in un test di integrazione — usare questo.
    """

    def _wait(check: Callable[[], bool], *, tries: int = 15, delay: float = 0.4) -> bool:
        from backend.workers.graph_worker import drain_once

        return _drain_until([drain_once], check, tries, delay)

    return _wait


@pytest.fixture(autouse=True)
def _no_background_queue_workers(monkeypatch):
    """Nessun worker in-process durante i test: le code le drena il test.

    `TestClient(app)` fa partire il lifespan, che avvia i drain loop di
    ingest/graph/mem0 su un executor di modulo mai chiuso. Il loop viene
    cancellato all'uscita del context manager, ma una passata gia' partita
    finisce comunque - e puo' reclamare (`FOR UPDATE SKIP LOCKED`) il job che
    un test *successivo* ha appena accodato. Quel test vede `drain_once() == 0`
    e fallisce anche se il lavoro e' stato fatto: e' la flakiness che rendeva
    rossi `test_canonical_mirror` e `test_kg_ingest_queue` solo nella suite
    completa, e solo qualche volta.

    I test del supervisore restano validi: verificano il loop con callable
    finti e l'endpoint di stato, non il drain reale in background.
    """
    monkeypatch.setattr(settings, "workers_in_process", False)


@pytest.fixture()
def wait_ingested():
    """drain di `kg_ingest_queue` best-effort + retry finche' `check()` e' vero.

    Stessa regola di `wait_projected`, per l'altra coda: mai asserire sul valore
    di ritorno di `drain_once()` in un test di integrazione. Il conteggio dice
    *chi* ha fatto il lavoro, non *se* e' stato fatto, e con piu' consumatori
    sulla stessa coda quella e' una domanda a cui il test non deve tenere.
    """

    def _wait(check: Callable[[], bool], *, tries: int = 15, delay: float = 0.4) -> bool:
        from backend.workers.ingest_worker import drain_once

        return _drain_until([drain_once], check, tries, delay)

    return _wait


@pytest.fixture()
def wait_pipeline():
    """Come sopra, ma per la catena intera: `kg_ingest_queue` -> `graph_outbox`.

    Un test che parte dal tool e arriva a una retrieval attraversa due code in
    sequenza. Drenarne una sola e sperare che l'altra sia gia' passata e' il modo
    in cui questi test diventavano flaky.
    """

    def _wait(check: Callable[[], bool], *, tries: int = 15, delay: float = 0.4) -> bool:
        from backend.workers.graph_worker import drain_once as drain_graph
        from backend.workers.ingest_worker import drain_once as drain_ingest

        return _drain_until([drain_ingest, drain_graph], check, tries, delay)

    return _wait


@pytest.fixture(scope="session", autouse=True)
def _operational_schema():
    """Porta il database operativo `workspace` a head una volta per sessione.

    Niente DDL all'import dei moduli: lo schema si crea qui (o dal lifespan
    dell'app in prod). Skip se `WORKSPACE_DATABASE_URL` non e' configurata —
    i test che toccano workspace/chat/episodic si skippano da soli.
    """
    if not settings.workspace_database_url:
        return
    from backend.local_store import ensure_schema

    ensure_schema()


@pytest.fixture(autouse=False)
def mock_env(monkeypatch):
    """Override environment variables for testing without real API keys."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake-key-for-ci")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-fake-key-for-ci")
