# conftest.py — shared pytest fixtures
import time
from collections.abc import Callable

import pytest

from backend.settings import settings


def _drain_until(drains: list[Callable[[], int]], check: Callable[[], bool], tries: int, delay: float) -> bool:
    """
    Drain the supplied queues repeatedly until a condition succeeds or retries are exhausted.
    
    Parameters:
        drains (list[Callable[[], int]]): Queue-draining callables to invoke on each attempt.
        check (Callable[[], bool]): Condition evaluated after each draining attempt.
        tries (int): Maximum number of attempts.
        delay (float): Number of seconds to wait between unsuccessful attempts.
    
    Returns:
        bool: `True` if the condition succeeds, `False` otherwise.
    """
    for _ in range(tries):
        for drain in drains:
            drain()
        if check():
            return True
        time.sleep(delay)
    return False


@pytest.fixture()
def wait_projected():
    """
    Provide a helper that drains the graph outbox and retries until a condition succeeds.
    
    Returns:
        Callable: A function that accepts a condition and returns `True` when it succeeds
        within the configured retry limit, or `False` otherwise.
    """

    def _wait(check: Callable[[], bool], *, tries: int = 15, delay: float = 0.4) -> bool:
        """Drain the graph queue until a condition is met or the retry limit is reached.
        
        Parameters:
        	check (Callable[[], bool]): Condition to evaluate after draining.
        	tries (int): Maximum number of attempts.
        	delay (float): Seconds to wait between attempts.
        
        Returns:
        	bool: `True` if the condition succeeds, `False` otherwise.
        """
        from backend.workers.graph_worker import drain_once

        return _drain_until([drain_once], check, tries, delay)

    return _wait


@pytest.fixture(autouse=True)
def _no_background_queue_workers(monkeypatch):
    """Disable in-process queue workers so tests can control queue draining explicitly."""
    monkeypatch.setattr(settings, "workers_in_process", False)


@pytest.fixture()
def wait_ingested():
    """
    Provide a helper that drains the ingestion queue until a condition succeeds.
    
    Returns:
        A function that accepts a condition and optional retry settings, returning
        `True` when the condition succeeds and `False` after all attempts fail.
    """

    def _wait(check: Callable[[], bool], *, tries: int = 15, delay: float = 0.4) -> bool:
        """
        Retry a condition while draining the ingestion queue.
        
        Parameters:
            check (Callable[[], bool]): Condition to evaluate after each drain attempt.
            tries (int): Maximum number of attempts.
            delay (float): Seconds to wait between attempts.
        
        Returns:
            bool: `True` if the condition succeeds within the attempts, `False` otherwise.
        """
        from backend.workers.ingest_worker import drain_once

        return _drain_until([drain_once], check, tries, delay)

    return _wait


@pytest.fixture()
def wait_pipeline():
    """
    Provide a helper for waiting until the ingestion and graph-processing pipeline completes.
    
    Returns:
    	Callable: A helper that drains both queues in sequence and returns `true` when the supplied condition succeeds, or `false` after the configured retries are exhausted.
    """

    def _wait(check: Callable[[], bool], *, tries: int = 15, delay: float = 0.4) -> bool:
        """
        Drain the ingestion and graph queues until a condition succeeds.
        
        Parameters:
        	check (Callable[[], bool]): Condition to evaluate after draining the queues
        	tries (int): Maximum number of attempts
        	delay (float): Seconds to wait between attempts
        
        Returns:
        	bool: `True` if the condition succeeds, `False` otherwise
        """
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


# Client del provider costruiti una volta e tenuti in cache. Un test live che
# gira per primo lascerebbe in cache un client vero, e i test successivi
# chiamerebbero il provider anche con la chiave azzerata: la cache non rilegge i
# settings. Si svuotano a ogni test. `api/routes/audio.py` non e' in lista: la
# sua cache e' gia' chiavata sull'api key e si invalida da sola.
_CACHED_PROVIDER_CLIENTS: tuple[tuple[str, str], ...] = (
    ("backend.process_understanding", "_understanding_llm"),
    ("backend.process_understanding", "_quality_evaluator_llm"),
    ("backend.memory.procedural.extraction", "_extract_llm"),
    ("backend.memory.procedural.extraction", "_generalize_llm"),
    ("backend.memory.reranker", "build_reranker"),
    ("backend.memory.embeddings", "_client"),
)


def _drop_cached_provider_clients() -> None:
    """Svuota le cache dei client, solo per i moduli gia' importati.

    Il controllo su `sys.modules` evita di importare mezzo backend in un test
    che non lo tocca: la cache di un modulo non importato e' vuota per
    definizione.
    """
    import sys

    for module_name, attribute in _CACHED_PROVIDER_CLIENTS:
        module = sys.modules.get(module_name)
        if module is None:
            continue
        builder = getattr(module, attribute, None)
        cache_clear = getattr(builder, "cache_clear", None)
        if cache_clear is not None:
            cache_clear()

    entity_resolution = sys.modules.get("backend.memory.knowledge_graph.entity_resolution")
    if entity_resolution is not None:
        # Singleton a mano, non `lru_cache`: si azzera la variabile di modulo.
        entity_resolution._llm_singleton = None


@pytest.fixture(autouse=True)
def _provider_calls_are_opt_in(request, monkeypatch):
    """Un test non paga il modello vero, a meno che non lo dichiari.

    Prima i test live erano gated sulla presenza della chiave, quindi in
    sviluppo giravano sempre: ~220 giudizi di qualita' reali in due giorni, da
    tenant di test, fino a esaurire il credito. Qui il default e' invertito. Chi
    vuole spendere si marca `live_llm` e si esporta `DELIR_LIVE_LLM=1`
    (vedi `tests/live_llm.py`).

    Si azzerano i settings *e* le variabili d'ambiente: `langchain_openai`, se
    gli passi `api_key=None`, ricade su `OPENAI_API_KEY` dell'ambiente, e la
    chiave tornerebbe dentro dalla finestra.
    """
    if request.node.get_closest_marker("live_llm"):
        # Il test paga per scelta dichiarata. Ma le cache restano sue: il
        # prossimo test non deve ereditare il suo client vero.
        request.addfinalizer(_drop_cached_provider_clients)
        return

    monkeypatch.setattr(settings, "openai_api_key", None)
    monkeypatch.setattr(settings, "tavily_api_key", None)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    _drop_cached_provider_clients()


@pytest.fixture(autouse=True)
def _queues_stay_in_the_test_tenant(monkeypatch):
    """Una passata di coda, nei test, non lavora il workspace di un cliente.

    Le code del workspace (piani da ricostruire, confronti con le fonti) vivono
    in un database condiviso con i dati di sviluppo, e le passate prendono le
    righe piu' vecchie **di tutti i tenant**: un test che drena due righe puo'
    prendere il processo di un cliente, ricostruirne il piano e scriverne il
    rapporto. E' successo davvero il 2026-09-17: due processi reali sono rimasti
    presi in carico da una passata di test.

    Qui ogni lettura di coda viene vincolata al tenant che il test ha in mano.
    Chi vuole davvero drenare oltre il proprio confine lo chiede per nome, e
    allora e' una scelta dichiarata e non un effetto collaterale.
    """
    from backend import workspace_database as wd
    from backend.security import get_current_tenant_id

    for name in ("due_plan_materializations", "due_conformance_checks"):
        original = getattr(wd, name)

        def scoped(*args, _original=original, **kwargs):
            # `setdefault` non basta: il worker passa `only_tenant_id=None` per
            # nome, ed e' proprio la chiamata che deve restare dentro il confine.
            if not kwargs.get("only_tenant_id"):
                kwargs["only_tenant_id"] = get_current_tenant_id()
            return _original(*args, **kwargs)

        monkeypatch.setattr(wd, name, scoped)
