"""A2-2: piu' risorse per attivita', ognuna con la sua durata.

Il pannello scenario manda per ogni task la risorsa principale (``resource_id``)
e le altre che possono svolgerlo (``other_assignments``). La durata di ognuna si
traduce con le stesse regole della principale, e il motore riceve tutte le
assegnazioni: il caso va alla prima risorsa libera.
"""

from pathlib import Path

import pytest

from backend.schemas.simulation import CreateSimulationRunRequest
from backend.simulation.scenario_builder import build_prosimos_scenario

BPMN = (Path(__file__).resolve().parents[2] / "ops" / "prosimos" / "spike" / "p2p_mini.bpmn").read_text(encoding="utf-8")

RESOURCES = [
    {"id": "clerk", "name": "Impiegato", "cost_per_hour": 30, "amount": 1},
    {"id": "senior", "name": "Senior", "cost_per_hour": 60, "amount": 1},
]


def _request(approve_extra: list[dict] | None = None, **overrides) -> CreateSimulationRunRequest:
    return CreateSimulationRunRequest(
        total_cases=20,
        resources=RESOURCES,
        tasks=[
            {"element_id": "T_receive", "mean_seconds": 600, "resource_id": "clerk"},
            {"element_id": "T_approve", "mean_seconds": 1200, "resource_id": "clerk",
             "other_assignments": approve_extra or []},
            {"element_id": "T_pay", "mean_seconds": 900, "resource_id": "clerk"},
        ],
        **overrides,
    )


def _activity(scenario, element_id: str) -> dict:
    return next(a for a in scenario.model["activities"] if a["element_id"] == element_id)


def test_other_resources_become_assignments_with_their_own_duration():
    scenario = build_prosimos_scenario(bpmn_xml=BPMN, request=_request([
        {"resource_id": "senior", "mean_seconds": 600, "distribution": "fixed"},
    ]))

    assignments = _activity(scenario, "T_approve")["assignments"]
    assert [a["resource_id"] for a in assignments] == ["clerk", "senior"]
    assert assignments[1]["duration"] == {"kind": "fixed", "value": 600.0}
    assert assignments[1]["provenance"]["origin"] == "manual"

    # Il motore riceve entrambe le risorse per l'attivita'.
    approve = next(t for t in scenario.payload["task_resource_distribution"] if t["task_id"] == "T_approve")
    assert [r["resource_id"] for r in approve["resources"]] == ["clerk", "senior"]


def test_the_duration_of_another_resource_follows_the_same_defaults():
    scenario = build_prosimos_scenario(bpmn_xml=BPMN, request=_request([
        {"resource_id": "senior", "mean_seconds": 1000},
    ]))

    duration = _activity(scenario, "T_approve")["assignments"][1]["duration"]
    # Normale con dev. std al 10% e limiti a +-3 sigma, come la risorsa principale.
    assert duration == {"kind": "normal", "mean": 1000.0, "std": 100.0, "minimum": 700.0, "maximum": 1300.0}


def test_without_other_resources_the_scenario_does_not_change():
    plain = build_prosimos_scenario(bpmn_xml=BPMN, request=_request())

    assert len(_activity(plain, "T_approve")["assignments"]) == 1


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ([{"resource_id": "ghost", "mean_seconds": 600}], "non esiste più"),
        ([{"resource_id": "clerk", "mean_seconds": 600}], "compare due volte"),
        ([{"resource_id": "senior", "mean_seconds": 600},
          {"resource_id": "senior", "mean_seconds": 700}], "compare due volte"),
        ([{"resource_id": "senior", "mean_seconds": 600, "distribution": "uniform"}], "indica minimo e massimo"),
    ],
)
def test_another_resource_that_does_not_fit_is_refused_with_the_task_name(extra, message):
    with pytest.raises(ValueError, match=message) as error:
        build_prosimos_scenario(bpmn_xml=BPMN, request=_request(extra))
    assert "T_approve" in str(error.value) or "Approv" in str(error.value)


def test_the_run_keeps_every_resource_in_the_model_the_inspector_reads(api_client, new_bpmn_model, fake_engine):
    created = api_client.post(
        f"/v1/workspace/bpmn-models/{new_bpmn_model()}/simulation-runs",
        json={**_request([{"resource_id": "senior", "mean_seconds": 600}]).model_dump(mode="json"),
              "current_bpmn_xml": BPMN},
    )
    assert created.status_code == 200, created.text

    model = api_client.get(f"/v1/workspace/simulation-runs/{created.json()['id']}/model").json()["model"]
    approve = next(a for a in model["activities"] if a["element_id"] == "T_approve")
    assert [a["resource_id"] for a in approve["assignments"]] == ["clerk", "senior"]


def test_a_missing_resource_is_a_400_with_the_reason(api_client, new_bpmn_model, fake_engine):
    response = api_client.post(
        f"/v1/workspace/bpmn-models/{new_bpmn_model()}/simulation-runs",
        json={**_request([{"resource_id": "ghost", "mean_seconds": 600}]).model_dump(mode="json"),
              "current_bpmn_xml": BPMN},
    )
    assert response.status_code == 400
    assert "non esiste più" in response.json()["error"]["message"]
    assert fake_engine == []
