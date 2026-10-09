"""P0.3: la coda delle simulazioni su Postgres.

Oltre il massimo di run insieme una richiesta non viene piu' rifiutata: aspetta
il suo turno, e il consulente vede la posizione. Chi prende un run lo fa in modo
esclusivo, batte finche' gira, e un run il cui esecutore muore torna in coda.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from backend.schemas.simulation import CreateSimulationRunRequest
from backend.schemas.workspace import BpmnModelResponse
from backend.settings import settings
from backend.simulation import queue
from backend.simulation.models import ProsimosSimulationResult
from backend.simulation.service import SimulationCapacityError, drain_simulation_queue, prepare_simulation_run
from backend.simulation.storage import complete_simulation_run, get_simulation_run
from backend.workspace_storage import WorkspaceSimulationRun, workspace_connection

BPMN = (Path(__file__).resolve().parents[2] / "ops" / "prosimos" / "spike" / "p2p_mini.bpmn").read_text(encoding="utf-8")


@pytest.fixture()
def model(new_bpmn_model) -> BpmnModelResponse:
    return BpmnModelResponse(id=new_bpmn_model(), process_id="p", name="Coda", xml=BPMN)


def _enqueue(model: BpmnModelResponse, seed: int) -> dict:
    run, scenario, _ = prepare_simulation_run(
        bpmn_model=model, request=CreateSimulationRunRequest(total_cases=5, seed=seed, current_bpmn_xml=BPMN)
    )
    assert scenario is not None
    return run


def _row(run_id: int) -> WorkspaceSimulationRun:
    with workspace_connection() as session:
        return session.get(WorkspaceSimulationRun, run_id)


def _age_heartbeat(run_id: int, seconds: float) -> None:
    with workspace_connection() as session:
        row = session.get(WorkspaceSimulationRun, run_id)
        row.heartbeat_at = (datetime.now(UTC) - timedelta(seconds=seconds)).isoformat()


def test_a_run_waits_its_turn_and_shows_its_position(model, monkeypatch):
    monkeypatch.setattr(settings, "simulation_max_concurrent_runs", 1)
    first, second, third = (_enqueue(model, seed) for seed in (1, 2, 3))

    assert second["queue"] == {"state": "queued", "position": 2}
    claimed = queue.claim_next_run("w1")
    assert claimed is not None and claimed.run_id == first["id"]
    # Il motore e' pieno: nessun altro lo prende, e la coda si accorcia di uno.
    assert queue.claim_next_run("w2") is None
    assert get_simulation_run(first["id"])["queue"] == {"state": "running", "position": None}
    assert get_simulation_run(third["id"])["queue"] == {"state": "queued", "position": 2}
    # Il run porta con se' cio' che serve per eseguirlo, senza la richiesta HTTP.
    assert claimed.bpmn_xml and claimed.scenario.payload["task_resource_distribution"]
    assert (claimed.total_cases, claimed.seed) == (5, 1)


def test_the_drain_runs_the_queue_in_order(model, fake_engine, monkeypatch):
    monkeypatch.setattr(settings, "simulation_max_concurrent_runs", 1)
    runs = [_enqueue(model, seed) for seed in (1, 2, 3)]

    assert asyncio.run(drain_simulation_queue("w1")) == 3
    assert [request.seed for request in fake_engine] == [1, 2, 3]
    assert all(get_simulation_run(run["id"])["status"] == "completed" for run in runs)
    assert get_simulation_run(runs[0]["id"])["queue"] is None


def test_a_full_queue_is_a_429_with_the_reason(api_client, model, monkeypatch):
    monkeypatch.setattr(settings, "simulation_max_queued_runs", 1)
    monkeypatch.setattr("backend.api.routes.simulation.drain_simulation_queue", lambda: None)
    _enqueue(model, 1)

    with pytest.raises(SimulationCapacityError, match="1 simulazioni in attesa"):
        _enqueue(model, 2)
    response = api_client.post(
        f"/v1/workspace/bpmn-models/{model.id}/simulation-runs",
        json={"total_cases": 5, "seed": 3, "current_bpmn_xml": BPMN},
    )
    assert response.status_code == 429
    assert "in attesa" in response.json()["error"]["message"]


def test_a_run_whose_worker_stops_beating_goes_back_in_the_queue(model):
    run = _enqueue(model, 1)
    assert queue.claim_next_run("dead").run_id == run["id"]

    _age_heartbeat(run["id"], settings.simulation_heartbeat_seconds * queue.MISSED_BEATS + 5)
    retaken = queue.claim_next_run("alive")
    assert retaken is not None and retaken.run_id == run["id"]
    assert _row(run["id"]).attempts == 2

    # Il vecchio esecutore torna in vita e consegna: e' tardi, il run e' di un altro.
    late = complete_simulation_run(run_id=run["id"], result=ProsimosSimulationResult(), worker_id="dead")
    assert late["status"] == "pending"


def test_after_the_last_attempt_the_run_fails_and_says_why(model):
    run = _enqueue(model, 1)
    for worker in ("w1", "w2"):
        assert queue.claim_next_run(worker).run_id == run["id"]
        _age_heartbeat(run["id"], settings.simulation_heartbeat_seconds * queue.MISSED_BEATS + 5)

    closed = get_simulation_run(run["id"])
    assert closed["status"] == "failed"
    assert closed["error"] == queue.STALE_RUN_ERROR
    assert queue.claim_next_run("w3") is None


def test_a_beating_run_is_never_taken_away(model):
    run = _enqueue(model, 1)
    claimed = queue.claim_next_run("w1")
    _age_heartbeat(run["id"], settings.simulation_heartbeat_seconds)  # un battito di ritardo, non tre
    assert queue.beat(claimed.run_id, "w1") is True
    assert queue.claim_next_run("w2") is None
    assert queue.beat(claimed.run_id, "w2") is False


def test_a_run_from_before_the_queue_is_closed_like_before(model):
    run = _enqueue(model, 1)
    old = (datetime.now(UTC) - timedelta(seconds=settings.prosimos_timeout_seconds + 300)).isoformat()
    with workspace_connection() as session:
        row = session.get(WorkspaceSimulationRun, run["id"])
        # Come la 0034 lascia un run pending gia' presente: avviato, senza battito ne' BPMN.
        row.started_at, row.heartbeat_at, row.bpmn_xml = old, None, None

    closed = get_simulation_run(run["id"])
    assert closed["status"] == "failed"
    assert closed["error"] == queue.LEGACY_STALE_RUN_ERROR


def test_the_api_returns_the_queue_state_of_a_waiting_run(api_client, model, monkeypatch):
    monkeypatch.setattr("backend.api.routes.simulation.drain_simulation_queue", lambda: None)
    created = api_client.post(
        f"/v1/workspace/bpmn-models/{model.id}/simulation-runs",
        json={"total_cases": 5, "seed": 9, "current_bpmn_xml": BPMN},
    )
    assert created.status_code == 200, created.text
    assert created.json()["queue"]["state"] == "queued"
    listed = api_client.get(f"/v1/workspace/bpmn-models/{model.id}/simulation-runs").json()
    assert listed[0]["queue"]["state"] == "queued"
