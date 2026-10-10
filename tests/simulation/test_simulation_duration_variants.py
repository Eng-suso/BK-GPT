"""SIM-32: durate che dipendono da un attributo a categorie del caso.

Il motore non le esegue: lo scenario compila l'attivita' in varianti dietro una
decisione per regola. Il run conserva il modello come l'ha scritto il consulente.
"""

from pathlib import Path

import pytest

from backend.schemas.simulation import CreateSimulationRunRequest
from backend.simulation.bpmn_normalizer import normalize_bpmn_for_prosimos
from backend.simulation.scenario_builder import build_prosimos_scenario, parse_bpmn_for_simulation

BPMN = normalize_bpmn_for_prosimos(
    (Path(__file__).resolve().parents[2] / "ops" / "prosimos" / "spike" / "p2p_mini.bpmn").read_text(encoding="utf-8")
)
TYPE = {"name": "tipo", "options": [{"value": "premium", "probability": 0.3}, {"value": "standard", "probability": 0.7}]}
AMOUNT = {"name": "importo", "distribution": {"kind": "uniform", "minimum": 100, "maximum": 12000}}


def _request(duration_by: dict, attributes: list[dict] | None = None) -> CreateSimulationRunRequest:
    return CreateSimulationRunRequest(
        total_cases=10,
        tasks=[
            {"element_id": "T_receive", "mean_seconds": 600},
            {"element_id": "T_approve", "mean_seconds": 1200, "duration_by": duration_by},
            {"element_id": "T_pay", "mean_seconds": 600},
        ],
        model_patch={"case_attributes": attributes if attributes is not None else [TYPE]},
    )


BY_TYPE = {"attribute": "tipo", "variants": [{"value": "premium", "mean_seconds": 600, "distribution": "fixed"}]}


def test_the_engine_gets_one_variant_per_category_behind_a_rule_based_decision():
    scenario = build_prosimos_scenario(bpmn_xml=BPMN, request=_request(BY_TYPE))

    tasks, gateways = parse_bpmn_for_simulation(scenario.bpmn_xml)
    assert [t.id for t in tasks if t.name == "Approva"] == ["T_approve", "T_approve__dur_1"]
    split = next(g for g in scenario.payload["gateway_branching_probabilities"] if g["gateway_id"] == "T_approve__dur_split")
    assert len(split["probabilities"]) == 2
    rules = {r["id"]: r["rules"] for r in scenario.payload["branch_rules"]}
    assert [[{"attribute": "tipo", "comparison": "!=", "value": "premium"}]] in rules.values()
    assert [[{"attribute": "tipo", "comparison": "=", "value": "premium"}]] in rules.values()
    variant = next(t for t in scenario.payload["task_resource_distribution"] if t["task_id"] == "T_approve__dur_1")
    assert variant["resources"][0]["distribution_name"] == "fix"
    # Il modello del run e' quello del consulente: una sola attivita', con le durate per categoria.
    approve = next(a for a in scenario.model["activities"] if a["element_id"] == "T_approve")
    assert approve["duration_by"]["variants"][0]["value"] == "premium"
    assert all(a["element_id"] != "T_approve__dur_1" for a in scenario.model["activities"])


def test_without_conditional_durations_nothing_is_rewritten():
    scenario = build_prosimos_scenario(bpmn_xml=BPMN, request=CreateSimulationRunRequest(
        total_cases=10, tasks=[{"element_id": t, "mean_seconds": 600} for t in ("T_receive", "T_approve", "T_pay")]))
    assert scenario.bpmn_xml is None


@pytest.mark.parametrize(
    ("duration_by", "attributes", "message"),
    [
        ({"attribute": "canale", "variants": [{"value": "web", "mean_seconds": 60}]}, [TYPE], "che il caso non ha"),
        ({"attribute": "importo", "variants": [{"value": "alto", "mean_seconds": 60}]}, [TYPE, AMOUNT], "solo da un attributo a categorie"),
        ({"attribute": "tipo", "variants": [{"value": "gold", "mean_seconds": 60}]}, [TYPE], "categorie che «tipo» non ha: gold"),
        ({"attribute": "tipo", "variants": [{"value": "premium", "mean_seconds": 60, "distribution": "uniform"}]}, [TYPE], "categoria «premium»"),
    ],
)
def test_a_conditional_duration_that_does_not_fit_is_refused_with_the_reason(duration_by, attributes, message):
    with pytest.raises(ValueError, match=message):
        build_prosimos_scenario(bpmn_xml=BPMN, request=_request(duration_by, attributes))


def test_the_run_keeps_the_conditional_durations_and_runs_the_rewritten_bpmn(api_client, new_bpmn_model, fake_engine):
    created = api_client.post(
        f"/v1/workspace/bpmn-models/{new_bpmn_model()}/simulation-runs",
        json={**_request(BY_TYPE).model_dump(mode="json"), "current_bpmn_xml": BPMN},
    )
    assert created.status_code == 200, created.text
    assert "T_approve__dur_1" in fake_engine[0].bpmn_xml
    model = api_client.get(f"/v1/workspace/simulation-runs/{created.json()['id']}/model").json()["model"]
    approve = next(a for a in model["activities"] if a["element_id"] == "T_approve")
    assert approve["duration_by"]["attribute"] == "tipo"


def test_a_generated_id_that_already_exists_is_refused():
    clash = BPMN.replace('<task id="T_pay"', '<task id="T_approve__dur_1"').replace('"T_pay"', '"T_approve__dur_1"')
    with pytest.raises(ValueError, match="contiene già l'id T_approve__dur_1"):
        build_prosimos_scenario(bpmn_xml=clash, request=CreateSimulationRunRequest(
            total_cases=10,
            tasks=[
                {"element_id": "T_receive", "mean_seconds": 600},
                {"element_id": "T_approve", "mean_seconds": 1200, "duration_by": BY_TYPE},
                {"element_id": "T_approve__dur_1", "mean_seconds": 600},
            ],
            model_patch={"case_attributes": [TYPE]},
        ))
