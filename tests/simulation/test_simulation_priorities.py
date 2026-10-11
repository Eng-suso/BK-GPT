"""SIM-12: le priorita' dei casi dal pannello, come ``priority_rules`` della patch.

Il motore le esegue gia' (``test_priority_rules_from_the_ir_serve_premium_first``):
qui si verifica che dalla richiesta v1 arrivino al payload e al modello del run.
"""

from pathlib import Path

import pytest

from backend.schemas.simulation import CreateSimulationRunRequest
from backend.simulation.scenario_builder import build_prosimos_scenario

BPMN = (Path(__file__).resolve().parents[2] / "ops" / "prosimos" / "spike" / "p2p_mini.bpmn").read_text(encoding="utf-8")

TYPE = {"name": "tipo", "options": [{"value": "premium", "probability": 0.2}, {"value": "standard", "probability": 0.8}],
        "provenance": {"origin": "manual"}}


def _premium_first(value: str = "premium") -> dict:
    return {"case_attributes": [TYPE], "priority_rules": [
        {"level": 1, "condition": {"any_of": [[{"attribute": "tipo", "operator": "=", "value": value}]]}},
    ]}


def _request(**overrides) -> CreateSimulationRunRequest:
    return CreateSimulationRunRequest(
        total_cases=20,
        tasks=[{"element_id": t, "mean_seconds": 600} for t in ("T_receive", "T_approve", "T_pay")],
        **overrides,
    )


def test_priorities_reach_the_engine_payload():
    scenario = build_prosimos_scenario(bpmn_xml=BPMN, request=_request(model_patch=_premium_first()))
    assert scenario.payload["prioritisation_rules"] == [
        {"priority_level": 1, "rules": [[{"attribute": "tipo", "comparison": "=", "value": "premium"}]]},
    ]


def test_a_priority_on_an_attribute_the_case_does_not_have_is_refused():
    patch = {"priority_rules": _premium_first()["priority_rules"]}
    with pytest.raises(ValueError, match="attributi che il caso non ha: tipo"):
        build_prosimos_scenario(bpmn_xml=BPMN, request=_request(model_patch=patch))


def test_the_run_keeps_the_priorities_in_the_model_the_inspector_reads(api_client, new_bpmn_model, fake_engine):
    created = api_client.post(
        f"/v1/workspace/bpmn-models/{new_bpmn_model()}/simulation-runs",
        json={**_request().model_dump(mode="json"), "current_bpmn_xml": BPMN, "model_patch": _premium_first()},
    )
    assert created.status_code == 200, created.text
    model = api_client.get(f"/v1/workspace/simulation-runs/{created.json()['id']}/model").json()["model"]
    assert model["priority_rules"][0]["level"] == 1
    assert model["priority_rules"][0]["condition"]["any_of"][0][0]["value"] == "premium"


def test_an_invalid_priority_is_a_400_with_the_reason(api_client, new_bpmn_model, fake_engine):
    response = api_client.post(
        f"/v1/workspace/bpmn-models/{new_bpmn_model()}/simulation-runs",
        json={**_request().model_dump(mode="json"), "current_bpmn_xml": BPMN,
              "model_patch": {"priority_rules": _premium_first()["priority_rules"]}},
    )
    assert response.status_code == 400
    assert "tipo" in response.json()["error"]["message"]
    assert fake_engine == []
