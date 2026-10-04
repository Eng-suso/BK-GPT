"""Lo stato della proiezione di un cliente: fresco, indietro, o non si sa.

Senza database: la coda di proiezione si sostituisce, si guarda solo come
le sue statistiche diventano uno stato. `UNKNOWN` non deve mai uscire come
`FRESH` - e' il difetto che il gateway aveva: un errore di lettura della coda
tornava `None`, che voleva dire anche "tutto a posto".
"""

from __future__ import annotations

import pytest

from backend.memory import projection_health
from backend.memory.projection_health import ProjectionHealth, projection_report
from backend.settings import settings

_HEALTHY = {"pending": 3, "stuck": 0, "dead_letter": 0, "oldest_pending_age_s": 1.0}


@pytest.fixture(autouse=True)
def _worker_dsn(monkeypatch):
    monkeypatch.setattr(settings, "canonical_worker_url", "postgresql+psycopg://w@h/db")
    projection_health.clear_cache()
    yield
    projection_health.clear_cache()


def _queue(monkeypatch, stats=None, error: Exception | None = None) -> None:
    from backend.workers import graph_worker

    def queue_stats(_client_id=None):
        if error is not None:
            raise error
        return stats

    monkeypatch.setattr(graph_worker, "queue_stats", queue_stats)


def test_a_healthy_queue_is_fresh(monkeypatch):
    _queue(monkeypatch, _HEALTHY)

    report = projection_report("client-1")

    assert report.health is ProjectionHealth.FRESH
    assert report.readable


@pytest.mark.parametrize(
    "change",
    [{"dead_letter": 1}, {"stuck": 2}, {"oldest_pending_age_s": 10_000.0}],
)
def test_a_lagging_queue_is_stale_and_says_why(monkeypatch, change):
    _queue(monkeypatch, {**_HEALTHY, **change})

    report = projection_report("client-1")

    assert report.health is ProjectionHealth.STALE
    assert not report.readable
    assert report.reason


def test_an_unreadable_queue_is_unknown_not_fresh(monkeypatch):
    _queue(monkeypatch, error=RuntimeError("permission denied for table graph_outbox"))

    report = projection_report("client-1")

    assert report.health is ProjectionHealth.UNKNOWN
    assert not report.readable


def test_without_the_worker_dsn_nobody_can_verify(monkeypatch):
    monkeypatch.setattr(settings, "canonical_worker_url", None)

    report = projection_report("client-1")

    assert report.health is ProjectionHealth.UNKNOWN
    assert not report.readable
