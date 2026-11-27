"""B3.2: le cause delle attese nei KPI di un log reale (``waitingCauses``)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.eventlog.kpi import summarize, waiting_causes
from backend.eventlog.model import CanonicalEvent, EventLog

MONDAY = datetime(2023, 1, 2, tzinfo=UTC)


def at(day: int, hour: float) -> datetime:
    return MONDAY + timedelta(days=day, hours=hour)


def _log(with_start: bool = True) -> EventLog:
    events = []
    for day in range(5):  # una settimana: la stessa persona lavora 9-17
        case = f"c{day}"
        events += [
            CanonicalEvent(case, "Ricevi", at(day, 10), at(day, 9.5) if with_start else None, resource="ana"),
            # Ana e' occupata in un altro caso fino alle 12: "Controlla" aspetta lei.
            CanonicalEvent(f"x{day}", "Altro", at(day, 12), at(day, 10.5) if with_start else None, resource="ana"),
            CanonicalEvent(case, "Controlla", at(day, 13), at(day, 12) if with_start else None, resource="ana"),
            # "Paga" aspetta un fornitore: Bruno lavora dalle 9 ed e' libero dalle 13 alle 16.
            CanonicalEvent(f"y{day}", "Archivia", at(day, 9.5), at(day, 9) if with_start else None, resource="bruno"),
            CanonicalEvent(case, "Paga", at(day, 16.5), at(day, 16) if with_start else None, resource="bruno"),
        ]
    return EventLog(origin="real", events=tuple(events))


def test_each_activity_has_its_waiting_split_by_cause():
    causes = summarize(_log(), {"Controlla": "Task_check", "Paga": "Task_pay"})["waitingCauses"]
    rows = {row["name"]: row for row in causes["activities"]}
    assert rows["Controlla"]["el"] == "Task_check"
    assert rows["Controlla"]["seconds"]["contention"] == 5 * 1.5 * 3600
    assert rows["Paga"]["seconds"]["extraneous"] == 5 * 3 * 3600
    assert rows["Paga"]["waiting"] == rows["Paga"]["executions"] == 5
    assert [row["name"] for row in causes["activities"]][:2] == ["Paga", "Controlla"]  # chi aspetta di piu' prima


def test_without_start_times_the_causes_are_absent_not_zero():
    assert waiting_causes(_log(with_start=False), {}) is None


def test_a_person_seen_once_a_day_gets_a_narrow_schedule():
    """Limite noto (B3.2): l'orario si scopre da quando la persona compare nel log.

    Chi compare solo alle 16 ha un orario 16-17, e l'attesa prima conta come fuori orario.
    Seguito proposto in docs/vpt/LOG.md (orario comune per i gruppi con pochi eventi).
    """
    events = [e for e in _log().events if e.activity != "Archivia"]
    rows = {row["name"]: row for row in waiting_causes(EventLog(origin="real", events=tuple(events)), {})["activities"]}
    assert rows["Paga"]["seconds"]["unavailability"] == 5 * 3 * 3600
