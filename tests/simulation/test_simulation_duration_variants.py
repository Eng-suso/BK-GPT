"""SIM-32: durate che dipendono da un attributo a categorie del caso.

Il motore non le esegue: lo scenario compila l'attivita' in varianti dietro una
decisione per regola. Il run conserva il modello come l'ha scritto il consulente.
"""

import json
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
        ({"attribute": "importo", "variants": [{"value": "alto", "mean_seconds": 60}]}, [TYPE, AMOUNT], "richiedono un attributo a categorie"),
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


def test_an_attribute_update_on_the_activity_runs_on_every_variant():
    # Un caso che passa da una copia completa la stessa attivita': l'aggiornamento
    # dell'attributo deve valere anche li', altrimenti i premium non lo ricevono.
    request = _request(BY_TYPE).model_copy(update={"model_patch": {
        "case_attributes": [TYPE],
        "attribute_updates": [{"element_id": "T_approve", "name": "approvato", "expression": "1"}],
    }})
    request = CreateSimulationRunRequest.model_validate(request.model_dump())
    scenario = build_prosimos_scenario(bpmn_xml=BPMN, request=request)

    updated = {entry["event_id"] for entry in scenario.payload["event_attributes"]}
    assert updated == {"T_approve", "T_approve__dur_1"}
    assert [u["element_id"] for u in scenario.model["attribute_updates"]] == ["T_approve"]


# --- soglie su un attributo numerico ------------------------------------------------

BY_AMOUNT = {"attribute": "importo", "variants": [
    {"up_to": 1000, "mean_seconds": 300, "distribution": "fixed"},
    {"up_to": 5000, "mean_seconds": 900, "distribution": "fixed"},
]}


def test_thresholds_on_a_number_become_consecutive_bands_behind_the_decision():
    scenario = build_prosimos_scenario(bpmn_xml=BPMN, request=_request(BY_AMOUNT, [AMOUNT]))

    rules = sorted(json.dumps(r["rules"]) for r in scenario.payload["branch_rules"] if r["id"].startswith("T_approve__dur_split"))
    assert rules == sorted(json.dumps(r) for r in [
        [[{"attribute": "importo", "comparison": ">=", "value": "5000"}]],
        [[{"attribute": "importo", "comparison": "<", "value": "1000"}]],
        [[{"attribute": "importo", "comparison": ">=", "value": "1000"}, {"attribute": "importo", "comparison": "<", "value": "5000"}]],
    ])
    variants = {t["task_id"]: t["resources"][0]["distribution_params"][0]["value"]
                for t in scenario.payload["task_resource_distribution"] if t["task_id"].startswith("T_approve__dur_")}
    assert variants == {"T_approve__dur_1": 300.0, "T_approve__dur_2": 900.0}
    approve = next(a for a in scenario.model["activities"] if a["element_id"] == "T_approve")
    assert [v["up_to"] for v in approve["duration_by"]["variants"]] == [1000.0, 5000.0]


@pytest.mark.parametrize(("duration_by", "attributes", "message"), [
    (BY_AMOUNT, [{"name": "importo", "options": [{"value": "alto", "probability": 1}]}], "le soglie richiedono un attributo numerico"),
    ({"attribute": "importo", "variants": [{"up_to": 5000, "mean_seconds": 300}, {"up_to": 1000, "mean_seconds": 600}]}, [AMOUNT], "le soglie devono crescere"),
    ({"attribute": "importo", "variants": [{"up_to": 5000, "mean_seconds": 300}, {"value": "x", "mean_seconds": 600}]}, [AMOUNT], "o tutte per categoria o tutte per soglia"),
])
def test_thresholds_that_do_not_fit_are_refused(duration_by, attributes, message):
    with pytest.raises(ValueError, match=message):
        build_prosimos_scenario(bpmn_xml=BPMN, request=_request(duration_by, attributes))
