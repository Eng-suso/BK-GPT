"""B3.2: test dell'attribuzione delle attese e del banco (senza rete, senza venv di ricerca)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import UTC, datetime

import pytest

from tests.simulation.benchmark.b3_2 import attribution_eval, report, run
from tests.simulation.benchmark.b3_2.attribution import (
    BPMN_NS,
    Calendar,
    Execution,
    add_timers,
    attribute,
    concurrent_pairs,
    discover_calendars,
    enablements,
    extraneous_delays,
    fit_duration,
)

MONDAY = datetime(2023, 1, 2, tzinfo=UTC).timestamp()
H = 3600.0
NINE_TO_FIVE = Calendar([(d * 86400 + 9 * H, d * 86400 + 17 * H) for d in range(5)])


def at(day: int, hour: float) -> float:
    return MONDAY + day * 86400 + hour * H


def ex(case: str, activity: str, start: float, end: float, resource: str = "r") -> Execution:
    return Execution(case, activity, start, end, resource)


def test_calendar_counts_off_time_and_finds_the_last_open_instant():
    assert NINE_TO_FIVE.off_within(at(0, 16), at(1, 10)) == pytest.approx(16 * H)
    assert NINE_TO_FIVE.last_on_before(at(1, 8)) == pytest.approx(at(0, 17))
    assert NINE_TO_FIVE.last_on_before(at(0, 10)) == at(0, 10)
    assert Calendar(always=True).off_within(at(0, 0), at(3, 0)) == 0


def test_resource_busy_with_other_work_is_contention():
    log = [
        ex("a", "A", at(0, 9), at(0, 10), "x"),
        ex("b", "Other", at(0, 9.5), at(0, 12), "r"),
        ex("a", "B", at(0, 12), at(0, 13), "r"),  # pronta alle 10, r occupata fino alle 12
    ]
    waiting = attribute(log, calendars={"x": NINE_TO_FIVE, "r": NINE_TO_FIVE})[2]
    assert waiting.enabled == at(0, 10)
    assert waiting.seconds["contention"] == pytest.approx(2 * H)
    assert waiting.dominant() == "contention"


def test_resource_off_shift_is_unavailability_and_idle_time_before_is_extraneous():
    log = [ex("a", "A", at(0, 15), at(0, 16), "x"), ex("a", "B", at(1, 9), at(1, 10), "r")]
    waiting = attribute(log, calendars={"x": NINE_TO_FIVE, "r": NINE_TO_FIVE})[1]
    assert waiting.seconds["unavailability"] == pytest.approx(16 * H)
    assert waiting.seconds["extraneous"] == pytest.approx(1 * H)  # 16-17: r libera e in orario
    assert waiting.dominant() == "unavailability"


def test_idle_resource_on_shift_is_an_extraneous_delay():
    log = [ex("a", "A", at(0, 9), at(0, 10), "x"), ex("a", "B", at(0, 14), at(0, 15), "r")]
    waiting = attribute(log, calendars={"x": NINE_TO_FIVE, "r": NINE_TO_FIVE})[1]
    assert waiting.seconds["extraneous"] == pytest.approx(4 * H)
    assert waiting.dominant() == "extraneous"


def test_executions_started_together_are_a_batch():
    log = [ex(c, "A", at(0, 9 + n) + 7.3, at(0, 9.5 + n), "x") for n, c in enumerate("abc")]
    log += [ex(c, "Send", at(0, 15) + 0.4 * n, at(0, 15.2), "r") for n, c in enumerate("abc")]
    waits = attribute(log, calendars={"x": NINE_TO_FIVE, "r": NINE_TO_FIVE})[3:]
    assert [w.dominant() for w in waits] == ["batching"] * 3
    assert waits[0].seconds["batching"] == pytest.approx(5.5 * H)


def test_starts_recorded_to_the_minute_are_never_a_batch():
    log = [ex(c, "A", at(0, 9 + n), at(0, 9.5 + n), "x") for n, c in enumerate("abc")]
    log += [ex(c, "Send", at(0, 15), at(0, 15.2), "r") for c in "abc"]
    assert {w.dominant() for w in attribute(log, calendars={"x": NINE_TO_FIVE, "r": NINE_TO_FIVE})[3:]} == {"extraneous"}


def test_an_execution_without_resource_still_enables_the_next_one():
    log = [ex("a", "A", at(0, 9), at(0, 10), "x"), ex("a", "B", at(0, 10), at(0, 12), ""), ex("a", "C", at(0, 13), at(0, 14), "r")]
    waits = attribute(log, calendars={"x": NINE_TO_FIVE, "r": NINE_TO_FIVE})
    assert waits[1].enabled is None  # la sua attesa non si spiega
    assert waits[2].enabled == at(0, 12) and waits[2].seconds["extraneous"] == pytest.approx(H)


def test_a_recorded_enablement_is_used_as_is():
    log = [ex("a", "A", at(0, 9), at(0, 10), "x"), Execution("a", "B", at(0, 13), at(0, 14), "r", enabled=at(0, 12))]
    assert attribute(log, calendars={"x": NINE_TO_FIVE, "r": NINE_TO_FIVE})[1].enabled == at(0, 12)


def test_first_execution_of_a_case_has_no_observable_enablement():
    assert attribute([ex("a", "A", at(0, 9), at(0, 10))])[0].enabled is None


def test_concurrent_activities_do_not_enable_each_other():
    log = []
    for n, case in enumerate("abcd"):
        log += [ex(case, "Start", at(n, 9), at(n, 9.5)), ex(case, "P", at(n, 10), at(n, 12)), ex(case, "Q", at(n, 11), at(n, 11.5))]
    pairs = concurrent_pairs(log)
    assert frozenset(("P", "Q")) in pairs
    assert enablements(log, pairs)[2] == at(0, 9.5)  # Q e' abilitata da Start, non da P


def test_calendars_are_discovered_per_group_with_the_working_day_filled():
    log = [ex(str(n), "A", at(n % 5, 9 + (n % 2) * 7), at(n % 5, 9.5 + (n % 2) * 7), f"clerk_{n % 2}") for n in range(20)]
    calendar = discover_calendars(log)["clerk_0"]
    assert calendar.is_on(at(0, 12))  # fra le 9 e le 16: giornata senza buchi
    assert not calendar.is_on(at(0, 20)) and not calendar.is_on(at(5, 12))


def test_fit_duration_picks_a_prosimos_distribution():
    assert fit_duration([60.0] * 5)["distribution_name"] == "fix"
    assert fit_duration([0.0, 0.0, 0.0, 0.0, 1000.0])["distribution_name"] == "lognorm"
    expon = fit_duration([10.0, 20.0, 5.0, 40.0, 1.0, 25.0, 3.0, 60.0])
    assert expon["distribution_name"] in ("expon", "lognorm")


def test_delays_only_for_activities_that_wait_often():
    log = [ex(c, "A", at(0, 9), at(0, 9.1), "x") for c in "abcd"] + [ex(c, "B", at(0, 13), at(0, 13.1), f"r{c}") for c in "abcd"]
    delays = extraneous_delays(log, attribute(log, calendars={}))
    assert set(delays) == {"B"}


BPMN = f"""<?xml version="1.0"?>
<definitions xmlns="{BPMN_NS}"><process id="p">
<startEvent id="s"><outgoing>f1</outgoing></startEvent>
<task id="t1" name="Check"><incoming>f1</incoming><outgoing>f2</outgoing></task>
<endEvent id="e"><incoming>f2</incoming></endEvent>
<sequenceFlow id="f1" sourceRef="s" targetRef="t1"/><sequenceFlow id="f2" sourceRef="t1" targetRef="e"/>
</process></definitions>"""


def test_add_timers_puts_a_timer_on_the_incoming_flow():
    text, events = add_timers(BPMN, {"Check": fit_duration([60.0, 60.0])})
    q = lambda tag: f"{{{BPMN_NS}}}{tag}"  # noqa: E731
    process = ET.fromstring(text).find(q("process"))
    timer = process.find(q("intermediateCatchEvent"))
    flows = {f.get("id"): (f.get("sourceRef"), f.get("targetRef")) for f in process.findall(q("sequenceFlow"))}
    assert flows["f1"] == ("s", timer.get("id"))
    assert (timer.get("id"), "t1") in flows.values()
    assert events == [{"event_id": timer.get("id"), "activity": "Check", "distribution_name": "fix", "distribution_params": [{"value": 60.0}]}]


def test_new_configs_do_not_change_g3b():
    from tests.simulation.benchmark.g3b import run as g3b

    assert "simod_fixed_extr" not in g3b.CONFIGS and "simod_attr_extr" not in g3b.CONFIGS
    assert run.CONFIGS["simod_extr"] == g3b.CONFIGS["simod_extr"]


def test_report_cards_use_the_written_primaries():
    primaries = {(n, card.candidate, card.primary) for n, card, _ in report.CARDS}
    assert ("1", "simod_fixed_extr", "relative_event") in primaries
    assert {("3", "simod_attr_extr", "cycle_time_w1"), ("3", "simod_attr_extr", "relative_event")} <= primaries


def test_truth_calendars_read_the_model_json():
    calendars = attribution_eval.true_calendars("Loan_Application_5_timers_after")
    assert calendars  # le varianti _after usano il JSON di _5_timers
    assert any(not c.always for c in calendars.values())


def test_identical_results_are_a_tie_and_g3b_is_left_alone():
    from tests.simulation.benchmark.g3b import report as g3b_report

    same = {"status": "measured", "metrics": {"relative_event": {"mean": 0.0, "ci95": 0.0}}}
    assert report.compare(same, same, "relative_event") == "pari"
    assert g3b_report.compare(same, same, "relative_event") == "perde"  # comportamento di G3b, invariato
    with report._ties_for_identical():
        assert g3b_report.compare is report.compare
    assert g3b_report.compare is report._g3b_compare


def test_fit_closest_prefers_the_family_of_the_sample():
    import random

    from tests.simulation.benchmark.b3_2.attribution import fit_closest

    rng = random.Random(1)
    assert fit_closest([rng.uniform(100, 200) for _ in range(500)])["distribution_name"] == "uniform"
    assert fit_closest([rng.expovariate(1 / 300) for _ in range(500)])["distribution_name"] == "expon"
    assert fit_closest([max(0.0, rng.gauss(1000, 50)) for _ in range(500)])["distribution_name"] == "norm"
