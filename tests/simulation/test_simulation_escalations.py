"""SIM-35: escalation a tempo da un timer interrompente sul bordo di un'attivita'.

Il motore non esegue i boundary event: il normalizer ne fa una decisione dopo
l'attivita', lo scenario la compila con la quota dei casi che superano il timer.
"""

import math
from pathlib import Path

import pytest

from backend.schemas.simulation import CreateSimulationRunRequest
from backend.simulation.bpmn_normalizer import normalize_bpmn_for_prosimos
from backend.simulation.ir.escalations import exceed_probability
from backend.simulation.ir.model import Exponential, Fixed, Gamma, LogNormal, Normal, Uniform
from backend.simulation.scenario_builder import (
    baseline_for_bpmn,
    build_prosimos_scenario,
    parse_bpmn_for_simulation,
)
from backend.simulation.timers import duration_seconds

SPIKE = (Path(__file__).resolve().parents[2] / "ops" / "prosimos" / "spike" / "p2p_mini.bpmn").read_text(encoding="utf-8")


def escalation_bpmn(timer: str = "<timeDuration>PT30M</timeDuration>", cancel: str = "") -> str:
    """Approva ha un timer di 30 minuti: chi scade passa da Sollecita e poi al pagamento."""
    return SPIKE.replace(
        '<exclusiveGateway id="G_join"/>',
        f'<boundaryEvent id="B_late" name="Oltre 30 minuti" attachedToRef="T_approve"{cancel}>'
        f"<timerEventDefinition>{timer}</timerEventDefinition></boundaryEvent>"
        '<task id="T_remind" name="Sollecita"/><exclusiveGateway id="G_join"/>',
    ).replace(
        '<sequenceFlow id="F_back" sourceRef="T_approve" targetRef="G_join"/>',
        '<sequenceFlow id="F_back" sourceRef="T_approve" targetRef="G_join"/>'
        '<sequenceFlow id="F_late" sourceRef="B_late" targetRef="T_remind"/>'
        '<sequenceFlow id="F_reminded" sourceRef="T_remind" targetRef="G_join"/>',
    )


def _request(**approve) -> CreateSimulationRunRequest:
    return CreateSimulationRunRequest(total_cases=10, tasks=[
        {"element_id": "T_receive", "mean_seconds": 600},
        {"element_id": "T_approve", "mean_seconds": 1500, "distribution": "uniform", "min_seconds": 600, "max_seconds": 2400, **approve},
        {"element_id": "T_remind", "mean_seconds": 300},
        {"element_id": "T_pay", "mean_seconds": 600},
    ])


@pytest.mark.parametrize(("text", "seconds"), [
    ("PT48H", 172_800), ("P2D", 172_800), ("P1DT12H", 129_600), ("PT30M", 1800), ("P1W", 604_800),
    ("P1M", None), ("P", None), ("PT", None), ("PT0S", None), ("R3/PT1H", None), (None, None),
])
def test_only_fixed_iso_durations_are_read(text, seconds):
    assert duration_seconds(text) == seconds


def test_the_normalizer_turns_the_timer_into_a_decision_after_the_activity():
    bpmn = normalize_bpmn_for_prosimos(escalation_bpmn())
    _, gateways = parse_bpmn_for_simulation(bpmn)
    late = next(g for g in gateways if g.id == "B_late")
    assert late.name == "Oltre 30 minuti"
    assert {f.id for f in late.outgoing_flows} == {"F_back", "F_late"}
    assert late.escalation is not None
    assert late.escalation.model_dump() == {"activity_id": "T_approve", "after_seconds": 1800.0, "normal_flow_id": "F_back"}
    # Il ramo d'escalation resta: Sollecita e' un'attivita' da simulare.
    tasks, _ = parse_bpmn_for_simulation(bpmn)
    assert "T_remind" in {t.id for t in tasks}
    assert baseline_for_bpmn(bpmn).gateways[-1].escalation == late.escalation


@pytest.mark.parametrize("bpmn", [
    escalation_bpmn(cancel=' cancelActivity="false"'),
    escalation_bpmn(timer="<timeCycle>R3/PT1H</timeCycle>"),
    escalation_bpmn(timer="<timeDate>2026-12-01T09:00:00Z</timeDate>"),
], ids=["non-interrupting", "cycle", "date"])
def test_other_timers_are_still_removed(bpmn):
    _, gateways = parse_bpmn_for_simulation(normalize_bpmn_for_prosimos(bpmn))
    assert all(g.id != "B_late" for g in gateways)


@pytest.mark.parametrize(("distribution", "after", "expected"), [
    (Fixed(value=1200), 1000, 1.0),
    (Fixed(value=1200), 1200, 0.0),
    (Uniform(minimum=600, maximum=2400), 1800, 1 / 3),
    (Uniform(minimum=600, maximum=2400), 3000, 0.0),
    (Uniform(minimum=600, maximum=2400), 300, 1.0),
    # Esponenziale troncata in [0, 10 000] con media 1000.
    (Exponential(mean=1000, minimum=0, maximum=10_000), 2000,
     (math.exp(-2) - math.exp(-10)) / (1 - math.exp(-10))),
    # Normale simmetrica nei limiti: la media divide a meta'.
    (Normal(mean=1000, std=100, minimum=700, maximum=1300), 1000, 0.5),
    # Lognormale: la mediana e' exp(mu).
    (LogNormal(mean=1000, variance=250_000, minimum=0, maximum=1e9),
     math.exp(math.log(1000) - math.log(1.25) / 2), 0.5),
    # Gamma con forma 1 = esponenziale con la stessa media.
    (Gamma(mean=1000, variance=1_000_000, minimum=0, maximum=1e9), 2000, math.exp(-2)),
    # Gamma con forma 4: P(X > 6000) con scala 1000, dalla somma di Poisson.
    (Gamma(mean=4000, variance=4_000_000, minimum=0, maximum=1e9), 6000,
     sum(math.exp(-6) * 6**k / math.factorial(k) for k in range(4))),
])
def test_the_share_that_outlasts_the_timer_matches_how_the_engine_samples(distribution, after, expected):
    assert exceed_probability(distribution, after) == pytest.approx(expected, abs=1e-6)


def test_the_engine_gets_the_share_up_front_a_capped_activity_and_a_timed_out_copy():
    scenario = build_prosimos_scenario(bpmn_xml=normalize_bpmn_for_prosimos(escalation_bpmn()), request=_request())

    split = next(g for g in scenario.payload["gateway_branching_probabilities"] if g["gateway_id"] == "T_approve__timer_split")
    shares = {p["path_id"]: float(p["value"]) for p in split["probabilities"]}
    assert shares["T_approve__timer_split__T_approve__timeout"] == pytest.approx(1 / 3)
    durations = {t["task_id"]: t["resources"][0] for t in scenario.payload["task_resource_distribution"]}
    # In tempo: la stessa uniforme fino a 30 minuti. Scaduti: esattamente 30 minuti.
    assert [p["value"] for p in durations["T_approve"]["distribution_params"]] == [600.0, 1800.0]
    assert durations["T_approve__timeout"] == {"resource_id": durations["T_approve"]["resource_id"],
                                               "distribution_name": "fix", "distribution_params": [{"value": 1800.0}]}
    assert 'id="F_back" sourceRef="T_approve"' in scenario.bpmn_xml
    assert 'id="F_late" sourceRef="T_approve__timeout"' in scenario.bpmn_xml
    assert 'id="B_late"' not in scenario.bpmn_xml
    # Una sola Approva nel log: la copia ha lo stesso nome e viene dopo.
    tasks, _ = parse_bpmn_for_simulation(scenario.bpmn_xml)
    assert [t.id for t in tasks if t.name == "Approva"] == ["T_approve", "T_approve__timeout"]
    # Il run conserva la decisione del BPMN con il suo timer.
    late = next(g for g in scenario.model["gateways"] if g["element_id"] == "B_late")
    assert late["escalation"]["after_seconds"] == 1800.0


def test_an_activity_that_never_outlasts_the_timer_never_escalates():
    scenario = build_prosimos_scenario(bpmn_xml=normalize_bpmn_for_prosimos(escalation_bpmn()),
                                       request=_request(max_seconds=1500))
    split = next(g for g in scenario.payload["gateway_branching_probabilities"] if g["gateway_id"] == "T_approve__timer_split")
    assert {p["path_id"]: float(p["value"]) for p in split["probabilities"]}["T_approve__timer_split__T_approve__timeout"] == 0.0


def test_a_rework_on_the_activity_composes_with_its_escalation():
    scenario = build_prosimos_scenario(bpmn_xml=normalize_bpmn_for_prosimos(escalation_bpmn()), request=_request(
        rework={"back_to": "T_approve", "probability": 0.2, "max_repeats": 1}))
    # Il ritorno parte dal ramo in tempo e torna davanti alla scelta del timer.
    assert 'sourceRef="T_approve" targetRef="T_approve__rework"' in scenario.bpmn_xml
    assert 'sourceRef="T_approve__rework_join" targetRef="T_approve__timer_split"' in scenario.bpmn_xml


def test_the_compatibility_report_declares_the_escalation_as_approximated():
    from backend.simulation.compatibility import bpmn_compatibility_report

    report = bpmn_compatibility_report(escalation_bpmn())
    late = next(e for e in report.elements if e.element_id == "B_late")
    assert (late.status, late.impact) == ("approximated", "medium")
    assert "attesa in coda" in late.note
    # Il ramo d'escalation ora si simula.
    remind = next(e for e in report.elements if e.element_id == "T_remind")
    assert remind.status == "preserved"
