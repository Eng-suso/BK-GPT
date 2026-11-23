from datetime import datetime, timedelta, timezone

import pytest

from backend.eventlog.model import CanonicalEvent, EventLog
from backend.eventlog.kpi import summarize
from backend.eventlog.validation import validate


BASE = datetime(2026, 1, 5, 9, tzinfo=timezone.utc)


def event(case: str, activity: str, enabled: int | None, start: int | None, end: int) -> CanonicalEvent:
    return CanonicalEvent(
        case_id=case, activity=activity,
        enabled=BASE + timedelta(minutes=enabled) if enabled is not None else None,
        start=BASE + timedelta(minutes=start) if start is not None else None,
        end=BASE + timedelta(minutes=end),
    )


def test_validation_excludes_unobservable_first_wait_and_uses_replications():
    real = EventLog(origin="real", events=(event("1", "A", None, 0, 2), event("1", "B", None, 8, 10)))
    sim = EventLog(origin="simulated", events=(event("1", "A", -7, 0, 2), event("1", "B", 2, 8, 10)))
    result = validate(real, [(80, sim), (81, sim)])
    assert result["kpis"]["cycle"]["real"] == 600
    assert result["kpis"]["cycle"]["bias"] == 0
    assert result["kpis"]["between"]["bias"] == 0
    assert result["firstWaitSimulated"]["mean"] == 420
    assert result["distances"]["cycleW1"]["mean"] == 0
    assert result["distances"]["ngd"]["mean"] == 0
    assert result["replications"] == 2


def test_validation_rejects_missing_starts_without_partial_result():
    real = EventLog(origin="real", events=(event("1", "A", None, None, 2),))
    sim = EventLog(origin="simulated", events=(event("1", "A", 0, 0, 2),))
    with pytest.raises(ValueError, match="inizio"):
        validate(real, [(80, sim)])


def test_control_flow_distance_detects_changed_path():
    real = EventLog(origin="real", events=(event("1", "A", None, 0, 2), event("1", "B", None, 2, 4)))
    sim = EventLog(origin="simulated", events=(event("1", "A", 0, 0, 2), event("1", "C", 2, 2, 4)))
    assert validate(real, [(80, sim)])["distances"]["ngd"]["mean"] > 0


def test_real_summary_marks_unobserved_enablement():
    real = EventLog(origin="real", events=(event("1", "A", None, 0, 2), event("1", "B", None, 2, 4)))
    summary = summarize(real)
    assert summary["firstEnableObserved"] is False
    assert summary["enablementObserved"] is False
