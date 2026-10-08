"""A2-1: la richiesta v1 porta una ``model_patch`` con cio' che i suoi campi non dicono.

Il pannello scenario traduce durate, risorse e calendari nei campi v1 (il ponte
verso l'IR, #88); attributi del caso e rami per regola arrivano come patch
dell'IR, applicata al modello tradotto e verificata sul BPMN.
"""

from pathlib import Path

import pytest

from backend.schemas.simulation import CreateSimulationRunRequest
from backend.simulation.scenario_builder import build_prosimos_scenario

BPMN = (Path(__file__).resolve().parents[2] / "ops" / "prosimos" / "spike" / "p2p_mini.bpmn").read_text(encoding="utf-8")


def _rule(attribute: str, operator: str, value) -> dict:
    return {"any_of": [[{"attribute": attribute, "operator": operator, "value": value}]]}


def _patch(*, high=None, low=None, attributes=None) -> dict:
    return {
        "case_attributes": attributes if attributes is not None else [
            {"name": "importo", "distribution": {"kind": "uniform", "minimum": 100, "maximum": 12000},
             "provenance": {"origin": "manual"}},
            {"name": "tipo", "options": [{"value": "premium", "probability": 0.2}, {"value": "standard", "probability": 0.8}],
             "provenance": {"origin": "manual"}},
        ],
        "gateways": [{
            "element_id": "G_split",
            "branches": [
                {"flow_id": "F_high", "probability": 0.5, "condition": high or _rule("importo", ">", 5000),
                 "provenance": {"origin": "manual"}},
                {"flow_id": "F_low", "probability": 0.5, "condition": low or _rule("importo", "<=", 5000),
                 "provenance": {"origin": "manual"}},
            ],
        }],
    }


def _request(**overrides) -> CreateSimulationRunRequest:
    return CreateSimulationRunRequest(
        total_cases=20,
        tasks=[
            {"element_id": "T_receive", "mean_seconds": 600},
            {"element_id": "T_approve", "mean_seconds": 1200, "distribution": "lognorm", "std_seconds": 300},
            {"element_id": "T_pay", "mean_seconds": 900},
        ],
        **overrides,
    )


def test_the_patch_adds_case_attributes_and_branch_rules_to_the_translated_model():
    scenario = build_prosimos_scenario(bpmn_xml=BPMN, request=_request(model_patch=_patch()))

    payload = scenario.payload
    assert [a["name"] for a in payload["case_attributes"]] == ["importo", "tipo"]
    assert payload["branch_rules"][0]["rules"] == [[{"attribute": "importo", "comparison": ">", "value": "5000"}]]
    gateway = next(g for g in scenario.model["gateways"] if g["element_id"] == "G_split")
    assert gateway["branches"][0]["condition"]["any_of"][0][0]["attribute"] == "importo"
    # Le scelte dei campi v1 restano: la patch non tocca le durate.
    approve = next(a for a in scenario.model["activities"] if a["element_id"] == "T_approve")
    assert approve["assignments"][0]["duration"]["kind"] == "lognormal"


def test_without_a_patch_the_scenario_is_the_one_of_the_bridge():
    plain = build_prosimos_scenario(bpmn_xml=BPMN, request=_request())
    empty = build_prosimos_scenario(bpmn_xml=BPMN, request=_request(model_patch={}))

    assert empty.payload == plain.payload
    assert "branch_rules" not in plain.payload


@pytest.mark.parametrize(
    ("patch", "message"),
    [
        (_patch(high=_rule("canale", "=", "web")), "attributi che il caso non ha: canale"),
        ({"gateways": [{"element_id": "G_nope", "branches": [
            {"flow_id": "a", "probability": 0.5}, {"flow_id": "b", "probability": 0.5}]}]}, "gateway che il BPMN non ha: G_nope"),
        ({"gateways": [{"element_id": "G_split", "branches": [
            {"flow_id": "F_high", "probability": 0.5, "condition": _rule("importo", ">", 1)},
            {"flow_id": "F_low", "probability": 0.5}]}],
          "case_attributes": _patch()["case_attributes"]}, "o tutti i rami hanno una regola o nessuno"),
        ({"pools": "tutti"}, "pools"),
    ],
)
def test_a_patch_that_does_not_fit_is_refused_with_the_reason(patch, message):
    with pytest.raises(ValueError, match=message):
        build_prosimos_scenario(bpmn_xml=BPMN, request=_request(model_patch=patch))


def test_the_run_keeps_the_rules_in_the_model_the_inspector_reads(api_client, new_bpmn_model, fake_engine):
    created = api_client.post(
        f"/v1/workspace/bpmn-models/{new_bpmn_model()}/simulation-runs",
        json={**_request().model_dump(mode="json"), "current_bpmn_xml": BPMN, "model_patch": _patch()},
    )
    assert created.status_code == 200, created.text

    model = api_client.get(f"/v1/workspace/simulation-runs/{created.json()['id']}/model").json()["model"]
    assert [a["name"] for a in model["case_attributes"]] == ["importo", "tipo"]
    branches = next(g for g in model["gateways"] if g["element_id"] == "G_split")["branches"]
    assert [b["condition"]["any_of"][0][0]["operator"] for b in branches] == [">", "<="]
    assert branches[0]["provenance"]["origin"] == "manual"


def test_the_same_scenario_with_other_rules_is_another_run(api_client, new_bpmn_model, fake_engine):
    bpmn_model = new_bpmn_model()
    url = f"/v1/workspace/bpmn-models/{bpmn_model}/simulation-runs"
    base = {**_request().model_dump(mode="json"), "current_bpmn_xml": BPMN}
    first = api_client.post(url, json={**base, "model_patch": _patch()}).json()
    second = api_client.post(url, json={**base, "model_patch": _patch(
        high=_rule("importo", ">", 8000), low=_rule("importo", "<=", 8000))}).json()

    assert first["id"] != second["id"]


def test_a_bad_patch_is_a_400_with_the_reason(api_client, new_bpmn_model, fake_engine):
    response = api_client.post(
        f"/v1/workspace/bpmn-models/{new_bpmn_model()}/simulation-runs",
        json={**_request().model_dump(mode="json"), "current_bpmn_xml": BPMN,
              "model_patch": _patch(high=_rule("canale", "=", "web"))},
    )
    assert response.status_code == 400
    assert "canale" in response.json()["error"]["message"]
    assert fake_engine == []
