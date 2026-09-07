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


@pytest.fixture(autouse=False)
def mock_env(monkeypatch):
    """Override environment variables for testing without real API keys."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake-key-for-ci")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-fake-key-for-ci")
