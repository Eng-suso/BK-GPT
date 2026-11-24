"""Token-based replay del log reale sul BPMN."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from backend.eventlog.conformance import (
    ConformanceModelError,
    build_petri_net,
    check_conformance,
)
from backend.eventlog.model import CanonicalEvent, EventLog

NS = 'xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"'


def _bpmn(body: str) -> str:
    return f'<definitions {NS}><process id="P">{body}</process></definitions>'


def _flows(*edges: tuple[str, str]) -> str:
    return "".join(
        f'<sequenceFlow id="f{i}" sourceRef="{s}" targetRef="{t}"/>' for i, (s, t) in enumerate(edges)
    )


def _log(*traces: list[str]) -> EventLog:
    base = datetime(2026, 1, 1)
    events = []
    for case, trace in enumerate(traces):
        for step, activity in enumerate(trace):
            events.append(
                CanonicalEvent(case_id=f"c{case}", activity=activity, end=base + timedelta(hours=case, minutes=step))
            )
    return EventLog(origin="real", events=tuple(events))


IDENTITY = {name: name for name in "ABCDEFG"}

# Ordine d'acquisto: A richiesta, gateway sull'importo, B approvazione CFO o
# niente, C ordine emesso.
PURCHASE = _bpmn(
    '<startEvent id="s"/><task id="A" name="Richiesta"/><exclusiveGateway id="x"/>'
    '<task id="B" name="Approvazione CFO"/><exclusiveGateway id="j"/>'
    '<task id="C" name="Emissione ordine"/><endEvent id="e"/>'
    + _flows(("s", "A"), ("A", "x"), ("x", "B"), ("x", "j"), ("B", "j"), ("j", "C"), ("C", "e"))
)

# A, poi B e C in parallelo, poi D.
PARALLEL = _bpmn(
    '<startEvent id="s"/><task id="A"/><parallelGateway id="p"/><task id="B"/><task id="C"/>'
    '<parallelGateway id="q"/><task id="D"/><endEvent id="e"/>'
    + _flows(("s", "A"), ("A", "p"), ("p", "B"), ("p", "C"), ("B", "q"), ("C", "q"), ("q", "D"), ("D", "e"))
)


def test_traces_allowed_by_an_exclusive_choice_fit_perfectly():
    result = check_conformance(_log(["A", "B", "C"], ["A", "C"]), PURCHASE, IDENTITY)

    assert result.fitness == pytest.approx(1.0)
    assert result.fitting_cases == 2
    assert result.deviations == ()


def test_parallel_branches_fit_in_any_order():
    result = check_conformance(_log(["A", "B", "C", "D"], ["A", "C", "B", "D"]), PARALLEL, IDENTITY)

    assert result.fitness == pytest.approx(1.0)
    assert result.fitting_share == 1.0


def test_a_skipped_parallel_branch_leaves_the_model_waiting_for_it():
    result = check_conformance(_log(["A", "B", "D"]), PARALLEL, IDENTITY)

    variant = result.variants[0]
    assert not variant.fits
    assert variant.fitness < 1.0
    # D scatta senza il token di C: eseguita fuori ordine.
    assert variant.out_of_order == ("D",)
    # Il token prodotto per C resta: il modello aspettava ancora C.
    assert "C" in variant.waiting
    deviation = {d.element_id: d for d in result.deviations}
    assert deviation["D"].executed_out_of_order == 1
    assert deviation["C"].left_waiting == 1
    assert deviation["D"].cases_affected == 1


def test_swapped_sequence_is_counted_as_out_of_order():
    result = check_conformance(_log(["C", "A"]), PURCHASE, IDENTITY)

    assert result.variants[0].out_of_order[0] == "C"
    assert result.fitness <= 0.8


def test_fitness_is_weighted_by_cases_and_variants_by_frequency():
    log = _log(["A", "C"], ["A", "C"], ["A", "C"], ["C"])
    result = check_conformance(log, PURCHASE, IDENTITY)

    assert result.cases == 4
    assert result.fitting_cases == 3
    assert result.variants[0].activities == ("A", "C")
    assert result.variants[0].cases == 3
    assert 0.75 < result.fitness < 1.0


def test_unmapped_activities_are_reported_and_skipped():
    result = check_conformance(_log(["A", "Telefonata", "C"]), PURCHASE, {"A": "A", "C": "C"})

    assert result.unmodeled_activities == {"Telefonata": 1}
    variant = result.variants[0]
    assert variant.unmodeled == ("Telefonata",)
    assert variant.missing == 0 and variant.remaining == 0
    assert not variant.fits
    assert result.unobserved_elements == ("B",)


def test_an_unfinished_case_leaves_tokens_behind():
    result = check_conformance(_log(["A"]), PURCHASE, IDENTITY)

    variant = result.variants[0]
    assert variant.remaining >= 1
    assert variant.missing == 1  # la fine non e' mai raggiunta


def test_loops_through_an_exclusive_gateway_fit():
    model = _bpmn(
        '<startEvent id="s"/><exclusiveGateway id="m"/><task id="A"/><exclusiveGateway id="x"/>'
        '<task id="B"/><endEvent id="e"/>'
        + _flows(("s", "m"), ("m", "A"), ("A", "x"), ("x", "m"), ("x", "B"), ("B", "e"))
    )
    result = check_conformance(_log(["A", "A", "A", "B"]), model, IDENTITY)

    assert result.fitness == pytest.approx(1.0)


def test_inclusive_gateway_allows_one_or_both_branches():
    model = _bpmn(
        '<startEvent id="s"/><inclusiveGateway id="o"/><task id="A"/><task id="B"/>'
        '<inclusiveGateway id="j"/><task id="C"/><endEvent id="e"/>'
        + _flows(("s", "o"), ("o", "A"), ("o", "B"), ("A", "j"), ("B", "j"), ("j", "C"), ("C", "e"))
    )
    result = check_conformance(_log(["A", "C"], ["B", "A", "C"]), model, IDENTITY)

    assert result.fitness == pytest.approx(1.0)


def test_interrupting_boundary_event_replaces_the_activity():
    model = _bpmn(
        '<startEvent id="s"/><task id="A"/><boundaryEvent id="t" attachedToRef="A"/>'
        '<task id="B"/><task id="C"/><endEvent id="e1"/><endEvent id="e2"/>'
        + _flows(("s", "A"), ("A", "B"), ("B", "e1"), ("t", "C"), ("C", "e2"))
    )
    result = check_conformance(_log(["C"], ["A", "B"]), model, IDENTITY)

    assert result.fitness == pytest.approx(1.0)


def test_implicit_merge_and_split_on_activities():
    # B ha due ingressi (merge esclusivo implicito); A due uscite (split parallelo).
    model = _bpmn(
        '<startEvent id="s"/><task id="A"/><task id="B"/><task id="C"/><parallelGateway id="q"/>'
        '<endEvent id="e"/>'
        + _flows(("s", "A"), ("A", "B"), ("A", "C"), ("B", "q"), ("C", "q"), ("q", "e"))
    )
    result = check_conformance(_log(["A", "C", "B"]), model, IDENTITY)

    assert result.fitness == pytest.approx(1.0)


def test_the_process_with_the_mapped_activities_is_replayed():
    xml = (
        f"<definitions {NS}>"
        '<process id="Other"><startEvent id="s2"/><task id="Z"/><task id="Y"/><task id="W"/>'
        '<sequenceFlow id="g1" sourceRef="s2" targetRef="Z"/></process>'
        '<process id="P"><startEvent id="s"/><task id="A"/><endEvent id="e"/>'
        '<sequenceFlow id="f1" sourceRef="s" targetRef="A"/>'
        '<sequenceFlow id="f2" sourceRef="A" targetRef="e"/></process>'
        "</definitions>"
    )
    net = build_petri_net(xml, relevant_elements=["A"])

    assert net.activities == ["A"]
    assert [w.code for w in net.warnings] == ["multiple_processes"]


def test_variants_beyond_the_limit_are_excluded_and_counted():
    log = _log(["A", "C"], ["A", "C"], ["A", "B", "C"])
    result = check_conformance(log, PURCHASE, IDENTITY, max_variants=1)

    assert result.cases == 2
    assert result.excluded_variants == 1
    assert result.excluded_cases == 1


def test_unreadable_or_empty_models_are_refused():
    with pytest.raises(ConformanceModelError):
        build_petri_net("<not-xml")
    with pytest.raises(ConformanceModelError):
        build_petri_net(_bpmn('<startEvent id="s"/><endEvent id="e"/>' + _flows(("s", "e"))))


def _loan_app() -> tuple[EventLog, str]:
    import csv
    import gzip
    from pathlib import Path

    folder = Path(__file__).resolve().parents[2] / "datasets" / "simod" / "event-logs"
    with gzip.open(folder / "LoanApp_simplified.csv.gz", "rt", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    events = tuple(
        CanonicalEvent(
            case_id=row["case:concept:name"],
            activity=row["concept:name"],
            start=datetime.fromisoformat(row["start_timestamp"]),
            end=datetime.fromisoformat(row["time:timestamp"]),
        )
        for row in rows
    )
    xml = (folder / "LoanApp_simplified.bpmn").read_text(encoding="utf-8")
    return EventLog(origin="real", events=events), xml


def _same_name_mapping(log: EventLog, xml: str) -> dict[str, str | None]:
    by_name = {name: element for element, name in build_petri_net(xml).names.items()}
    return {activity: by_name.get(activity) for activity in log.activities()}


def test_a_log_simulated_from_the_model_fits_it():
    log, xml = _loan_app()
    result = check_conformance(log, xml, _same_name_mapping(log, xml))

    assert result.cases == 500
    assert result.fitting_cases == 500
    assert result.fitness == pytest.approx(1.0)


def test_skipped_appraisals_are_found_in_the_real_model():
    log, xml = _loan_app()
    skipped = {"0", "1", "2"}
    tampered = EventLog(
        origin="real",
        events=tuple(e for e in log.events if not (e.case_id in skipped and e.activity == "Appraise property")),
    )
    result = check_conformance(tampered, xml, _same_name_mapping(log, xml))

    assert result.fitting_cases == 497
    by_name = {d.name: d for d in result.deviations}
    assert by_name["Appraise property"].left_waiting == 3
    assert by_name["Assess loan risk"].executed_out_of_order == 3


def test_cases_affected_counts_each_case_once_per_element():
    # Un caso salta C (C resta in attesa), un altro fa D senza C: due casi diversi su D e C.
    log = _log(["A", "B", "D"], ["A", "B", "C", "D"], ["A", "C", "B", "D"])
    result = check_conformance(log, PARALLEL, IDENTITY)

    deviation = {d.element_id: d for d in result.deviations}
    assert deviation["D"].cases_affected == 1
    assert result.fitting_cases == 2


def test_warnings_carry_stable_codes():
    result = check_conformance(_log(["A", "C"]), PURCHASE, {"A": "A", "C": "C", "Gateway": "x"}, max_variants=1)

    assert [w.code for w in result.warnings] == ["mapped_to_non_activity"]
    assert result.warnings[0].params == {"activities": "Gateway"}
