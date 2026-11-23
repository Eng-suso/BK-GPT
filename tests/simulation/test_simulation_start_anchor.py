"""Count based replications must not depend on the wall clock of their worker."""

from types import SimpleNamespace

from backend.schemas.simulation import CreateSimulationRunRequest
from backend.simulation import service


def test_count_based_run_gets_a_fixed_start(monkeypatch):
    monkeypatch.setattr(service, "horizon_start", lambda value: value or "2026-11-23T00:00:00+00:00")
    request = CreateSimulationRunRequest(total_cases=1000)

    anchored = service._with_horizon(SimpleNamespace(xml=""), request)

    assert anchored.start_date == "2026-11-23T00:00:00+00:00"
    assert anchored.total_cases == 1000
    assert service._with_horizon(SimpleNamespace(xml=""), anchored).start_date == anchored.start_date


def test_explicit_start_is_preserved(monkeypatch):
    monkeypatch.setattr(service, "horizon_start", lambda value: value or "unused")
    request = CreateSimulationRunRequest(start_date="2023-01-02T09:00:00+00:00")

    assert service._with_horizon(SimpleNamespace(xml=""), request).start_date == request.start_date
