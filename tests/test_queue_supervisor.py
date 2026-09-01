"""Supervisore in-process delle code + endpoint di health.

Il loop di drain e' testato puro (callable finti). `queue_stats` e l'endpoint
sul path reale sono gated sul canonical.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from backend.settings import settings
from backend.workers import supervisor


def test_drain_loop_survives_errors_and_stops_on_cancel():
    calls = {"n": 0}

    def drain() -> int:
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("passata storta")
        return 1 if calls["n"] < 4 else 0

    async def run() -> None:
        task = asyncio.create_task(
            supervisor._drain_loop("t", drain, lambda: {"pending": 0, "stuck": 0}, 0.01)
        )
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())
    assert calls["n"] >= 4  # ha continuato dopo l'errore alla 2a passata


def test_run_queue_workers_noop_without_canonical(monkeypatch):
    monkeypatch.setattr(settings, "canonical_worker_url", None)
    # non deve sollevare ne' restare appeso
    asyncio.run(asyncio.wait_for(supervisor.run_queue_workers(), timeout=2))


def test_queues_endpoint_reports_status():
    from backend.app import app

    with TestClient(app) as client:
        body = client.get("/v1/observability/queues").json()

    if not settings.canonical_worker_url:
        assert body["status"] == "not_configured"
    else:
        assert body["status"] == "ok"
        assert set(body["graph_outbox"]) >= {"pending", "stuck"}
        assert set(body["mem0_projection_log"]) >= {"pending", "stuck"}


@pytest.mark.skipif(
    not settings.canonical_worker_url, reason="serve CANONICAL_WORKER_URL"
)
def test_queue_stats_and_prune_against_real_db():
    from backend.workers import graph_worker, mem0_worker

    for stats in (graph_worker.queue_stats(), mem0_worker.queue_stats()):
        assert set(stats) == {"pending", "stuck"}
        assert stats["pending"] >= 0 and stats["stuck"] >= 0

    # prune non tocca le righe pendenti (older_than futuro impossibile -> 0)
    assert graph_worker.prune(older_than_days=36500) == 0
    assert mem0_worker.prune(older_than_days=36500) == 0
