"""SIM-31b: l'esito di un'attivita' da' un attributo che le regole a valle leggono."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.schemas.simulation import CreateSimulationRunRequest
from backend.simulation.ir.model import AttributeUpdate, DiscreteOption
from backend.simulation.scenario_builder import build_prosimos_scenario

BPMN = (Path(__file__).resolve().parents[2] / "ops" / "prosimos" / "spike" / "p2p_mini.bpmn").read_text(encoding="utf-8")

KO_OK = [{"value": "KO", "probability": 0.3}, {"value": "OK", "probability": 0.7}]


def _when(value: str) -> dict:
    return {"any_of": [[{"attribute": "esito", "operator": "=", "value": value}]]}


def _request(outcome: dict | None = None, **patch) -> CreateSimulationRunRequest:
    receive = {"element_id": "T_receive", "mean_seconds": 600}
    if outcome is not None:
        receive["outcome"] = outcome
    return CreateSimulationRunRequest(
        tasks=[receive, {"element_id": "T_approve", "mean_seconds": 600}, {"element_id": "T_pay", "mean_seconds": 600}],
        model_patch=patch or None,
    )


ROUTE_ON_OUTCOME = {"gateways": [{"element_id": "G_split", "branches": [
    {"flow_id": "F_high", "probability": 0.5, "condition": _when("KO")},
    {"flow_id": "F_low", "probability": 0.5, "condition": _when("OK")},
]}]}


def test_the_outcome_is_compiled_as_a_discrete_event_attribute_the_gateway_reads():
    scenario = build_prosimos_scenario(
        bpmn_xml=BPMN, request=_request({"attribute": "esito", "options": KO_OK}, **ROUTE_ON_OUTCOME))

    assert scenario.payload["event_attributes"] == [{"event_id": "T_receive", "attributes": [
        {"name": "esito", "type": "discrete", "values": [{"key": "KO", "value": 0.3}, {"key": "OK", "value": 0.7}]},
    ]}]
    assert len(scenario.payload["branch_rules"]) == 2
    # Il modello del run porta l'esito, con la provenienza del pannello: l'inspector lo legge da qui.
    (update,) = scenario.model["attribute_updates"]
    assert update["element_id"] == "T_receive" and update["provenance"]["origin"] == "manual"


def test_a_rule_on_an_outcome_nobody_gives_is_refused():
    with pytest.raises(ValueError, match="esito"):
        build_prosimos_scenario(bpmn_xml=BPMN, request=_request(None, **ROUTE_ON_OUTCOME))


def test_an_outcome_cannot_take_the_name_of_a_case_attribute():
    patch = {"case_attributes": [{"name": "esito", "options": [{"value": "KO", "probability": 1}]}]}
    with pytest.raises(ValueError, match="attributo del caso"):
        build_prosimos_scenario(bpmn_xml=BPMN, request=_request({"attribute": "esito", "options": KO_OK}, **patch))


@pytest.mark.parametrize(("outcome", "message"), [
    ({"attribute": "delir_rework_1", "options": KO_OK}, "riservati"),
    ({"attribute": "esito", "options": [{"value": "KO", "probability": 0.5}, {"value": "KO", "probability": 0.5}]}, "duplicato"),
    ({"attribute": "esito", "options": [{"value": "KO", "probability": 0.5}]}, "sommano"),
])
def test_a_wrong_outcome_is_explained(outcome, message):
    with pytest.raises(ValueError, match=message):
        build_prosimos_scenario(bpmn_xml=BPMN, request=_request(outcome))


def test_an_outcome_on_an_element_that_is_not_an_activity_is_refused():
    request = _request()
    request.tasks.append(request.tasks[0].model_copy(update={
        "element_id": "G_split", "outcome": {"attribute": "esito", "options": KO_OK}}))
    request = CreateSimulationRunRequest.model_validate(request.model_dump())
    with pytest.raises(ValueError, match="non e' un'attivita'"):
        build_prosimos_scenario(bpmn_xml=BPMN, request=request)


def test_an_update_is_an_expression_or_categories_never_both():
    with pytest.raises(ValidationError):
        AttributeUpdate(element_id="T", name="x")
    with pytest.raises(ValidationError):
        AttributeUpdate(element_id="T", name="x", expression="1", options=(DiscreteOption(value="a", probability=1),))

