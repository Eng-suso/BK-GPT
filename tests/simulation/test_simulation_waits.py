"""SIM-11c: un timer intermedio con una durata fissa diventa un'attesa del caso.

Prima il normalizer lo toglieva e il report lo dichiarava: cycle time
sottostimato. Ora resta nel BPMN, il modello IR ha un'attesa con la durata
del timer e il motore la riceve in ``event_distribution``.
"""

import pytest

from backend.schemas.simulation import CreateSimulationRunRequest
from backend.simulation.bpmn_normalizer import normalize_bpmn_for_prosimos
from backend.simulation.compatibility import bpmn_compatibility_report
from backend.simulation.ir.model import Fixed, Wait
from backend.simulation.scenario_builder import (
    baseline_for_bpmn,
    build_prosimos_scenario,
    build_prosimos_scenario_from_model,
    parse_bpmn_waits,
)


def _bpmn(timer: str = "<bpmn:timeDuration>PT2H</bpmn:timeDuration>", *, after_event_gateway: bool = False) -> str:
    wait = f'<bpmn:intermediateCatchEvent id="W" name="Attendi 2 ore"><bpmn:timerEventDefinition>{timer}</bpmn:timerEventDefinition></bpmn:intermediateCatchEvent>'
    if after_event_gateway:
        body = f"""<bpmn:eventBasedGateway id="EG" />{wait}
<bpmn:intermediateCatchEvent id="M" name="Risposta"><bpmn:messageEventDefinition /></bpmn:intermediateCatchEvent>
<bpmn:sequenceFlow id="f2" sourceRef="A" targetRef="EG" /><bpmn:sequenceFlow id="f3" sourceRef="EG" targetRef="W" />
<bpmn:sequenceFlow id="f3b" sourceRef="EG" targetRef="M" /><bpmn:sequenceFlow id="f4" sourceRef="W" targetRef="B" />
<bpmn:sequenceFlow id="f4b" sourceRef="M" targetRef="B" />"""
    else:
        body = f"""{wait}<bpmn:sequenceFlow id="f2" sourceRef="A" targetRef="W" /><bpmn:sequenceFlow id="f3" sourceRef="W" targetRef="B" />"""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" id="D">
  <bpmn:process id="P" isExecutable="false">
    <bpmn:startEvent id="S" /><bpmn:task id="A" name="Invia sollecito" /><bpmn:task id="B" name="Chiama il cliente" /><bpmn:endEvent id="E" />
    <bpmn:sequenceFlow id="f1" sourceRef="S" targetRef="A" /><bpmn:sequenceFlow id="f5" sourceRef="B" targetRef="E" />
    {body}
  </bpmn:process>
</bpmn:definitions>"""


def _request() -> CreateSimulationRunRequest:
    return CreateSimulationRunRequest(total_cases=5, tasks=[{"element_id": t, "mean_seconds": 60, "distribution": "fixed"} for t in "AB"])


def test_a_timer_with_a_fixed_duration_stays_and_becomes_a_wait():
    bpmn = normalize_bpmn_for_prosimos(_bpmn())
    scenario = build_prosimos_scenario(bpmn_xml=bpmn, request=_request())

    assert 'id="W"' in bpmn
    assert [(w.id, w.seconds) for w in parse_bpmn_waits(bpmn)] == [("W", 7200.0)]
    [wait] = scenario.model["waits"]
    assert (wait["element_id"], wait["name"], wait["duration"]) == ("W", "Attendi 2 ore", {"kind": "fixed", "value": 7200.0})
    assert wait["provenance"]["origin"] == "declared"
    assert scenario.payload["event_distribution"] == [
        {"event_id": "W", "distribution_name": "fix", "distribution_params": [{"value": 7200.0}]},
    ]


@pytest.mark.parametrize("bpmn", [
    _bpmn(""),
    _bpmn("<bpmn:timeDate>2026-12-25T00:00:00Z</bpmn:timeDate>"),
    _bpmn("<bpmn:timeCycle>R3/PT1H</bpmn:timeCycle>"),
    _bpmn(after_event_gateway=True),
], ids=["senza durata", "una data", "un ciclo", "dopo un gateway a eventi"])
def test_other_timers_are_still_left_out(bpmn):
    normalized = normalize_bpmn_for_prosimos(bpmn)
    scenario = build_prosimos_scenario(bpmn_xml=normalized, request=_request())

    assert 'id="W"' not in normalized
    assert scenario.model["waits"] == []
    assert "event_distribution" not in scenario.payload


def test_the_report_says_the_timer_is_simulated_and_the_others_are_not():
    kept = {e.element_id: e for e in bpmn_compatibility_report(_bpmn()).elements}["W"]
    dated = {e.element_id: e for e in bpmn_compatibility_report(_bpmn("<bpmn:timeDate>2026-12-25T00:00:00Z</bpmn:timeDate>")).elements}["W"]

    assert (kept.status, kept.impact, kept.simulated_as) == ("preserved", "none", "timer")
    assert "orologio" in kept.note
    assert (dated.status, dated.impact) == ("removed", "high")


def test_the_baseline_and_a_v2_model_carry_the_wait_and_can_change_it():
    bpmn = normalize_bpmn_for_prosimos(_bpmn())
    baseline = baseline_for_bpmn(bpmn)
    assert [w.duration for w in baseline.waits] == [Fixed(value=7200.0)]

    longer = baseline.model_copy(update={"waits": (Wait(element_id="W", duration=Fixed(value=10_800)),)})
    scenario = build_prosimos_scenario_from_model(bpmn_xml=bpmn, model=longer)
    assert scenario.payload["event_distribution"][0]["distribution_params"] == [{"value": 10_800.0}]

    # Un modello che le ignora le riceve dal BPMN: il motore senza durata non partirebbe.
    plain = build_prosimos_scenario_from_model(bpmn_xml=bpmn, model=baseline.model_copy(update={"waits": ()}))
    assert plain.payload["event_distribution"][0]["event_id"] == "W"


def test_a_wait_on_an_element_that_is_not_a_timer_is_refused():
    bpmn = normalize_bpmn_for_prosimos(_bpmn())
    model = baseline_for_bpmn(bpmn).model_copy(update={"waits": (Wait(element_id="A", duration=Fixed(value=60)),)})

    with pytest.raises(ValueError, match="Attesa su un elemento che il BPMN non ha"):
        build_prosimos_scenario_from_model(bpmn_xml=bpmn, model=model)
