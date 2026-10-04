# conftest.py — shared pytest fixtures
import os
import socket
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest
from dotenv import dotenv_values

# --- I test non tracciano (L6, applicato a LangSmith) ------------------------
# Deve stare **prima** di importare `backend.settings`, che all'import esegue
# `configure_langsmith_environment()` e accende il tracing se `.env` dice true.
#
# Perche'. L6 dice che i test non devono consumare risorse del fornitore, e
# finora lo si era applicato solo a OpenAI (P0.1). LangSmith e' un fornitore
# come gli altri e ha una quota: il 2026-09-25 il registro delle tracce mostrava
# 5.069 tracce consumate fra l'1 e il 6 settembre, con un tetto mensile di
# 5.000. Da quel giorno ogni traccia del **prodotto** viene rifiutata con 429,
# cioe' i test hanno bruciato in sei giorni l'osservabilita' di tutto il mese.
#
# Chi vuole le tracce di una passata - gli eval col modello vero, dove vedere il
# giudizio serve davvero - le riaccende con `DELIR_TRACE_TESTS=1`.
if os.environ.get("DELIR_TRACE_TESTS", "").strip().lower() not in {"1", "true", "yes", "on"}:
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"

# --- I test non toccano mai lo stack di sviluppo -----------------------------
#
# Fino al 01/10 pytest leggeva i DSN dal `.env` di sviluppo e scriveva le sue
# fixture nel database dell'app: 22k righe finte in `mem0_projection_log`, che
# il worker mem0 ha poi mandato a OpenAI una per una all'avvio del prodotto.
#
# Regola: un DSN gia' presente nell'ambiente (CI, o chi lo esporta a mano) vince.
# Uno che arriva dal `.env` di sviluppo viene spostato sulla porta dello stack di
# test (`ops/docker-compose.test.yml`), che vive in tmpfs. Deve succedere qui, in
# cima, prima che `backend.settings` legga l'ambiente.

_DB_URL_KEYS = (
    "WORKSPACE_DATABASE_URL",
    "CANONICAL_DATABASE_URL",
    "CANONICAL_MIGRATOR_URL",
    "CANONICAL_WORKER_URL",
    "MEM0_DATABASE_URL",
)
_TEST_PG_PORT = int(os.environ.get("DELIR_TEST_PG_PORT", "55301"))
_TEST_NEO4J_PORT = int(os.environ.get("DELIR_TEST_NEO4J_PORT", "7688"))


# Lo stack di test nasce dagli script di `ops/postgres/init`: i nomi dei database
# sono i loro, non quelli che il `.env` di sviluppo puo' aver preso nel tempo.
_TEST_DB_NAMES = {"WORKSPACE_DATABASE_URL": "workspace"}


def _with_port(url: str, port: int, dbname: str | None = None) -> str:
    parts = urlsplit(url)
    userinfo, _, hostport = parts.netloc.rpartition("@")
    host = hostport.rsplit(":", 1)[0]
    netloc = f"{userinfo}@{host}:{port}" if userinfo else f"{host}:{port}"
    path = f"/{dbname}" if dbname else parts.path
    return urlunsplit(parts._replace(netloc=netloc, path=path))


def _development_env() -> dict[str, str | None]:
    """Il `.env` di sviluppo: quello della cartella corrente o, in un worktree
    che non ne ha uno, quello del checkout principale.

    Il secondo caso conta. In un worktree senza `.env` il confronto qui sotto
    non vedeva nulla da confrontare: chi caricava a mano il `.env` principale
    prima di pytest (il 2026-10-04) faceva girare i test sul database di
    sviluppo, tenant `local`, senza nessun avviso.
    """
    here = dotenv_values(".env")
    if here:
        return here
    try:
        common = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            capture_output=True, text=True, timeout=5, check=False,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return {}
    main_env = Path(common).resolve().parent / ".env" if common else None
    return dotenv_values(main_env) if main_env and main_env.is_file() else {}


def _point_at_test_stack() -> bool:
    """Sposta sullo stack di test i DSN presi dal `.env` di sviluppo.

    Ritorna True se ha spostato qualcosa: allora tocca a noi migrare lo stack.
    """
    dev = _development_env()
    moved = False
    for key in _DB_URL_KEYS:
        if os.environ.get(key):
            if os.environ[key] == dev.get(key):
                raise pytest.UsageError(
                    f"{key} punta al database di sviluppo: i test lo riempirebbero di fixture."
                )
            continue
        if dev.get(key):
            os.environ[key] = _with_port(dev[key], _TEST_PG_PORT, _TEST_DB_NAMES.get(key))
            moved = True
    if moved and not os.environ.get("NEO4J_URL"):
        os.environ["NEO4J_URL"] = f"bolt://127.0.0.1:{_TEST_NEO4J_PORT}"
    return moved


_USING_LOCAL_TEST_STACK = _point_at_test_stack()

# --- I test non chiamano il motore di simulazione vero ----------------------
#
# Con il `.env` di sviluppo i test che non sostituiscono l'adapter mandavano i
# run al Prosimos acceso in locale: run "in corso" per tutta la sessione, che
# riempivano il limite di simulazioni contemporanee e facevano fallire i test
# successivi con 429. In CI il motore non c'e' e il problema non si vedeva.
# Una porta chiusa fa fallire subito il run. Chi vuole il motore vero lo dice.
os.environ["PROSIMOS_BASE_URL"] = os.environ.get("DELIR_TEST_PROSIMOS_URL", "http://127.0.0.1:9")

from backend.settings import settings  # noqa: E402


def pytest_sessionstart(session):
    """Stack di test locale: deve essere acceso, e va migrato (vive in tmpfs)."""
    if not _USING_LOCAL_TEST_STACK:
        return
    try:
        socket.create_connection(("127.0.0.1", _TEST_PG_PORT), timeout=2).close()
    except OSError:
        pytest.exit(
            f"Stack di test spento (Postgres :{_TEST_PG_PORT}). Avvialo con:\n"
            "  cd ops && docker compose -f docker-compose.test.yml up -d --wait",
            returncode=4,
        )
    for args in (["upgrade", "head"], ["-c", "alembic_workspace.ini", "upgrade", "head"]):
        subprocess.run([sys.executable, "-m", "alembic", *args], check=True, env=os.environ.copy())


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
    ("backend.memory.reranker", "build_reranker"),
    ("backend.llm.gateway", "_embedding_client"),
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

    # `entity_resolution` non ha piu' niente da invalidare: da quando il giudizio
    # passa dal gateway, `build_llm()` non costruisce e non memoizza nessun
    # client - guarda se c'e' una chiave e restituisce un segnaposto.


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
        # Sul modello dei test, non su OpenAI: vedi `tests/live_llm.py`.
        from tests.live_llm import use_test_llm

        use_test_llm(monkeypatch)
        _drop_cached_provider_clients()
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
