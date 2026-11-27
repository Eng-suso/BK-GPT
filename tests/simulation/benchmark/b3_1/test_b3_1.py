"""B3.1: le varianti degli arrivi e i verdetti con le co-primarie, senza venv di ricerca."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from tests.simulation.benchmark import protocol
from tests.simulation.benchmark.b3_1 import arrivals, report
from tests.simulation.benchmark.log_distance import METRICS, Event

ROME = ZoneInfo("Europe/Rome")


@dataclass
class FakePhase:
    source_events: list[Event]
    cases: int
    start: datetime
    zone: ZoneInfo = field(default=ROME)


def _events(instants: list[datetime]) -> list[Event]:
    return [Event(f"c{n}", "a", t, t + timedelta(minutes=5)) for n, t in enumerate(instants)]


def _weekday_log(weeks: int = 4) -> list[datetime]:
    """Tre casi alle 9, 10, 11 di ogni giorno feriale, nessuno nel fine settimana."""
    monday = datetime(2026, 3, 2, tzinfo=ROME)  # attraversa il cambio d'ora del 29 marzo
    return [
        (monday + timedelta(days=d)).replace(hour=h).astimezone(UTC)
        for d in range(weeks * 7) if (monday + timedelta(days=d)).weekday() < 5 for h in (9, 10, 11)
    ]


def test_day_blocks_keep_weekday_hour_and_rate():
    start = datetime(2026, 4, 1, 10, 30, tzinfo=ROME).astimezone(UTC)  # mercoledi', dopo il cambio d'ora
    phase = FakePhase(_events(_weekday_log()), cases=20, start=start)
    got = arrivals.day_blocks(phase, seed=7)
    assert len(got) == 20 and got == sorted(got) and min(got) >= start
    local = [g.astimezone(ROME) for g in got]
    assert {t.hour for t in local} <= {9, 10, 11}  # ora locale conservata oltre il cambio d'ora
    assert all(t.weekday() < 5 for t in local)  # niente fine settimana
    assert local[0].hour == 11  # il primo giorno solo dopo il primo inizio
    assert (local[-1].date() - local[0].date()).days == 9  # 1 il primo giorno, poi 3 al giorno: 7 giorni feriali dopo (venerdi 10)
    assert arrivals.day_blocks(phase, seed=7) == got  # stesso seed, stessi arrivi


def test_recent_day_blocks_skip_the_quiet_past():
    quiet = [datetime(2025, 6, 2, 9, tzinfo=ROME).astimezone(UTC)]  # un caso un anno prima, poi niente
    busy = _weekday_log(weeks=5)
    start = busy[-1] + timedelta(hours=1)
    phase = FakePhase(_events(quiet + busy), cases=30, start=start)
    got = arrivals.recent_day_blocks(phase, seed=3)
    assert len(got) == 30 and (got[-1] - got[0]) < timedelta(days=14)  # tre al giorno feriale, non giorni vuoti
    assert {g.astimezone(ROME).hour for g in got} <= {9, 10, 11}


def test_day_blocks_fall_back_to_gaps_for_logs_of_a_few_hours():
    begin = datetime(2026, 3, 2, 9, tzinfo=UTC)
    phase = FakePhase(_events([begin + timedelta(minutes=2 * n) for n in range(50)]), cases=10,
                      start=begin + timedelta(hours=3), zone=ZoneInfo("UTC"))
    got = arrivals.day_blocks(phase, seed=1)
    assert got[0] == phase.start and len(got) == 10
    assert {b - a for a, b in zip(got, got[1:], strict=False)} == {timedelta(minutes=2)}


def _result(config: str, values: dict[str, float], val01: str = "supera") -> dict:
    metrics = {m: {"mean": values.get(m, 1.0), "ci95": 0.01, "replicas": [values.get(m, 1.0)] * 10} for m in METRICS}
    return {"status": "measured", "label": config, "identifiability": {m: protocol.IDENTIFIABLE for m in METRICS},
            "metrics": metrics, "cost": {"discovery_seconds": 10.0, "simulation_seconds": [1.0], "val01": val01}}


def _results(candidate: dict[str, float], val01: str = "supera") -> dict:
    found = {}
    for log in ("a", "b", "c"):
        found[(log, "validation", "simod_extr")] = _result("simod_extr", {})
        found[(log, "validation", "naive")] = _result("naive", {})
        found[(log, "validation", "simod_extr_days")] = _result("simod_extr_days", candidate, val01)
    return found


CARD = report.Card("C2", "simod_extr_days")


def test_go_needs_both_primaries():
    both = report.verdict(CARD, "validation", _results({"case_arrival": 0.5, "absolute_event": 0.5}), ["a", "b", "c"])
    assert both["verdict"] == "GO", both["reasons"]
    only_car = report.verdict(CARD, "validation", _results({"case_arrival": 0.5}), ["a", "b", "c"])
    assert only_car["verdict"] == "NO-GO"
    assert any("AED vince su 0/3" in r for r in only_car["reasons"])


def test_val01_is_compared_with_the_base():
    unsound = _results({"case_arrival": 0.5, "absolute_event": 0.5})
    for result in unsound.values():
        result["cost"]["val01"] = "non supera: ciclo"  # stesso scenario della base: non pesa sul componente
    assert report.verdict(CARD, "validation", unsound, ["a", "b", "c"])["verdict"] == "GO"
    differs = _results({"case_arrival": 0.5, "absolute_event": 0.5}, val01="non supera: ciclo")
    assert report.verdict(CARD, "validation", differs, ["a", "b", "c"])["verdict"] == "NO-GO"
