"""SIM-35: salti e rilavorazioni.

Il motore non li conosce: lo scenario li scrive come decisioni per regola nel
BPMN del motore. Il run conserva il modello come l'ha scritto il consulente.
"""

from pathlib import Path

import pytest

from backend.schemas.simulation import CreateSimulationRunRequest
from backend.simulation.bpmn_normalizer import normalize_bpmn_for_prosimos
from backend.simulation.scenario_builder import build_prosimos_scenario, parse_bpmn_for_simulation

BPMN = normalize_bpmn_for_prosimos(
    (Path(__file__).resolve().parents[2] / "ops" / "prosimos" / "spike" / "p2p_mini.bpmn").read_text(encoding="utf-8")
)
AMOUNT = {"name": "importo", "distribution": {"kind": "uniform", "minimum": 100, "maximum": 12000}}


def _request(**approve) -> CreateSimulationRunRequest:
    return CreateSimulationRunRequest(
        total_cases=10,
        tasks=[
            {"element_id": "T_receive", "mean_seconds": 600},
            {"element_id": "T_approve", "mean_seconds": 1200, **approve},
            {"element_id": "T_pay", "mean_seconds": 600},
        ],
        model_patch={"case_attributes": [AMOUNT]},
    )


def _gateway(scenario, gateway_id: str) -> dict[str, str]:
    gateway = next(g for g in scenario.payload["gateway_branching_probabilities"] if g["gateway_id"] == gateway_id)
    return {p["path_id"]: p for p in gateway["probabilities"]}


def _rules(scenario) -> dict[str, list]:
    return {r["id"]: r["rules"] for r in scenario.payload.get("branch_rules", [])}


def test_a_skipped_activity_gets_a_bypass_with_its_share():
    scenario = build_prosimos_scenario(bpmn_xml=BPMN, request=_request(skip={"probability": 0.3}))

    branches = _gateway(scenario, "T_approve__skip_split")
    assert branches["T_approve__skip_split__bypass"]["value"] == "0.3"
    assert float(branches["T_approve__skip_split__T_approve"]["value"]) == pytest.approx(0.7)
    assert "condition_id" not in branches["T_approve__skip_split__bypass"]
    # Il bypass porta all'unione dopo l'attivita', e da li' si prosegue come prima.
    assert 'id="T_approve__skip_split__bypass" sourceRef="T_approve__skip_split" targetRef="T_approve__skip_join"' in scenario.bpmn_xml
    assert 'id="F_back" sourceRef="T_approve__skip_join"' in scenario.bpmn_xml
    # Il run conserva il modello del consulente, con la provenienza del pannello.
    approve = next(a for a in scenario.model["activities"] if a["element_id"] == "T_approve")
    assert approve["skip"]["probability"] == 0.3
    assert approve["skip"]["provenance"]["origin"] == "manual"


def test_a_conditional_skip_applies_only_to_the_cases_that_match():
    small = {"any_of": [[{"attribute": "importo", "operator": "<", "value": 1000}]]}
    scenario = build_prosimos_scenario(bpmn_xml=BPMN, request=_request(skip={"probability": 1, "condition": small}))

    branches = _gateway(scenario, "T_approve__skip_split")
    rules = _rules(scenario)
    assert rules[branches["T_approve__skip_split__bypass"]["condition_id"]] == [
        [{"attribute": "importo", "comparison": "<", "value": "1000"}]]
    # L'altro ramo e' sempre vero: chi non soddisfa la regola fa l'attivita'.
    assert rules[branches["T_approve__skip_split__T_approve"]["condition_id"]] == [
        [{"attribute": "importo", "comparison": ">=", "value": "1000"}],
        [{"attribute": "importo", "comparison": "<", "value": "1000"}],
    ]


def test_a_rework_goes_back_with_its_share_up_to_the_limit():
    scenario = build_prosimos_scenario(bpmn_xml=BPMN, request=_request(
        rework={"back_to": "T_receive", "probability": 0.25, "max_repeats": 2}))

    branches = _gateway(scenario, "T_approve__rework")
    rules = _rules(scenario)
    assert branches["T_approve__rework__back"]["value"] == "0.25"
    assert rules[branches["T_approve__rework__back"]["condition_id"]] == [
        [{"attribute": "delir_rework_1", "comparison": "<", "value": "2"}]]
    assert len(rules[branches["F_back"]["condition_id"]]) == 2
    # Il contatore conta i completamenti dell'attivita'.
    assert {"event_id": "T_approve", "attributes": [
        {"name": "delir_rework_1", "type": "expression", "values": "delir_rework_1 + 1"}]} in scenario.payload["event_attributes"]
    # Si torna davanti a Ricevi, da dove passano anche i casi nuovi.
    assert 'id="F_start" sourceRef="S" targetRef="T_approve__rework_join"' in scenario.bpmn_xml
    assert 'id="T_approve__rework__back" sourceRef="T_approve__rework" targetRef="T_approve__rework_join"' in scenario.bpmn_xml
    tasks, _ = parse_bpmn_for_simulation(scenario.bpmn_xml)
    assert [t.id for t in tasks] == ["T_receive", "T_approve", "T_pay"]


def test_a_rework_rule_is_joined_with_the_limit():
    big = {"any_of": [[{"attribute": "importo", "operator": ">", "value": 5000}]]}
    scenario = build_prosimos_scenario(bpmn_xml=BPMN, request=_request(
        rework={"back_to": "T_approve", "probability": 0.5, "max_repeats": 1, "condition": big}))

    back = _gateway(scenario, "T_approve__rework")["T_approve__rework__back"]
    assert _rules(scenario)[back["condition_id"]] == [[
        {"attribute": "importo", "comparison": ">", "value": "5000"},
        {"attribute": "delir_rework_1", "comparison": "<", "value": "1"},
    ]]


def test_skip_rework_and_durations_by_category_compose():
    scenario = build_prosimos_scenario(bpmn_xml=BPMN, request=CreateSimulationRunRequest(
        total_cases=10,
        tasks=[
            {"element_id": "T_receive", "mean_seconds": 600},
            {"element_id": "T_approve", "mean_seconds": 1200,
             "skip": {"probability": 0.1},
             "rework": {"back_to": "T_approve", "probability": 0.2, "max_repeats": 3},
             "duration_by": {"attribute": "tipo", "variants": [{"value": "premium", "mean_seconds": 600}]}},
            {"element_id": "T_pay", "mean_seconds": 600},
        ],
        model_patch={"case_attributes": [
            {"name": "tipo", "options": [{"value": "premium", "probability": 0.5}, {"value": "standard", "probability": 0.5}]}]},
    ))
    # Le varianti stanno dentro il salto e dentro il ritorno; il contatore vale anche per loro.
    assert 'sourceRef="T_approve__skip_split" targetRef="T_approve__rework_join"' in scenario.bpmn_xml
    assert 'sourceRef="T_approve__rework_join" targetRef="T_approve__dur_split"' in scenario.bpmn_xml
    assert 'sourceRef="T_approve__dur_join" targetRef="T_approve__rework"' in scenario.bpmn_xml
    updated = {e["event_id"] for e in scenario.payload["event_attributes"]}
    assert updated == {"T_approve", "T_approve__dur_1"}


@pytest.mark.parametrize(("tasks", "message"), [
    ([{"element_id": "T_receive", "mean_seconds": 600,
       "rework": {"back_to": "T_pay", "probability": 0.2, "max_repeats": 1}}], "può tornare solo a un'attività che la precede"),
    ([{"element_id": "T_pay", "mean_seconds": 600,
       "rework": {"back_to": "G_join", "probability": 0.2, "max_repeats": 1}}], "non e' un'attivita'"),
])
def test_a_rework_that_cannot_go_back_is_refused_with_the_reason(tasks, message):
    with pytest.raises(ValueError, match=message):
        build_prosimos_scenario(bpmn_xml=BPMN, request=CreateSimulationRunRequest(total_cases=10, tasks=tasks))


def test_without_skips_or_reworks_nothing_is_rewritten():
    scenario = build_prosimos_scenario(bpmn_xml=BPMN, request=_request())
    assert scenario.bpmn_xml is None
