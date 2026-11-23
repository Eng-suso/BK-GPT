from types import SimpleNamespace
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException

from backend.api.routes import eventlog as route
from backend.eventlog.model import CanonicalEvent, EventLog
from backend.simulation.log_processor import LogEvent


def _run(run_id: int, group: str = "batch-a") -> dict:
    return {
        "id": run_id, "process_id": "process-1", "status": "completed",
        "request": {"replication_group": group, "replication_index": run_id - 79,
                    "workspace_scenario": {"id": 5, "revision": 415}, "bpmn_fingerprint": "same"},
        "summary": {"byActivity": [{"name": "A", "el": "Task_A"}]},
        "engine": "Prosimos", "result": {"Seed": run_id, "EngineVersion": "2.1"},
    }


def _prepare(monkeypatch, *, group_second: str = "batch-a"):
    real = EventLog(origin="real", events=())
    mapped = SimpleNamespace(
        event_log=SimpleNamespace(mapping=object()),
        activities=SimpleNamespace(matches=[]),
        quality=SimpleNamespace(rows_excluded=0, events_without_start=0),
    )
    monkeypatch.setattr(route.storage, "get_analysis", lambda _: mapped)
    monkeypatch.setattr(route.storage, "load_event_log_file", lambda _: (SimpleNamespace(name="real.csv", delimiter="," , process_id="process-1"), b"raw"))
    monkeypatch.setattr(route, "read_table", lambda *_: object())
    monkeypatch.setattr(route, "read_mapped_events", lambda *_args, **_kwargs: (real, None))
    monkeypatch.setattr(route, "get_simulation_run", lambda run_id: _run(run_id, group_second if run_id == 81 else "batch-a"))
    monkeypatch.setattr(route, "get_simulation_log_csv", lambda _: "csv")
    monkeypatch.setattr(route, "parse_prosimos_log", lambda _: [LogEvent("1", "A", 0, 1, 2, "r")])
    monkeypatch.setattr(route, "validate", lambda _real, generated: {"replications": len(generated)})


def test_validation_route_uses_same_replication_group(monkeypatch):
    _prepare(monkeypatch)
    result = route.validate_event_log("elog-1", [80, 81])
    assert result["replications"] == 2
    assert result["initialActivities"] == []
    assert result["provenance"]["runs"][1]["seed"] == 81


def test_validation_route_rejects_mixed_groups(monkeypatch):
    _prepare(monkeypatch, group_second="another-batch")
    with pytest.raises(HTTPException) as exc:
        route.validate_event_log("elog-1", [80, 81])
    assert exc.value.status_code == 422


def test_validation_route_identifies_initial_activity_after_bpmn_mapping(monkeypatch):
    _prepare(monkeypatch)
    analysis = route.storage.get_analysis("elog-1")
    analysis.activities.matches = [SimpleNamespace(activity="A", element_id="Task_A")]
    monkeypatch.setattr(route, "read_mapped_events", lambda *_args, **_kwargs: (
        EventLog(origin="real", events=(CanonicalEvent(
            case_id="case-1", activity="A", start=datetime(2023, 1, 2, 9, tzinfo=UTC),
            end=datetime(2023, 1, 2, 9, 1, tzinfo=UTC),
        ),)), None,
    ))

    result = route.validate_event_log("elog-1", [80])

    assert result["initialActivities"] == ["Task_A"]
