"""SIM-20a: ogni run conserva il modello IR che ha simulato, e l'API lo restituisce."""

from backend.simulation.ir.model import LogNormal, SimulationModel
from backend.simulation.ir.patch import ModelPatch
from tests.simulation.test_simulation_ir_contract import (  # noqa: F401 - fixture
    MINIMAL_BPMN,
    _bpmn_model_id,
    _capture_engine,
    client,
)


def _model_of(client, run_id: int) -> dict:
    response = client.get(f"/v1/workspace/simulation-runs/{run_id}/model")
    assert response.status_code == 200, response.text
    assert response.json()["run_id"] == run_id
    return response.json()["model"]


def test_a_patch_run_keeps_the_model_it_simulated_not_just_the_patch(client, monkeypatch):
    from backend.simulation.ir.model import Activity, Assignment

    _capture_engine(monkeypatch)
    patch = ModelPatch(activities=(
        Activity(element_id="Task_A", assignments=(
            Assignment(resource_id="delir-resource-operator", duration=LogNormal(
                mean=600, variance=90000, minimum=60, maximum=3600)),
        )),
    ))
    created = client.post(
        f"/v1/workspace/bpmn-models/{_bpmn_model_id(client)}/simulation-model-runs",
        json={"total_cases": 5, "current_bpmn_xml": MINIMAL_BPMN, "patch": patch.model_dump(mode="json")},
    )
    assert created.status_code == 200, created.text

    model = SimulationModel.model_validate(_model_of(client, created.json()["id"]))

    by_id = {activity.element_id: activity for activity in model.activities}
    assert by_id["Task_A"].assignments[0].duration.kind == "lognormal"
    # Il resto viene dalla baseline: c'e' anche se la richiesta non lo nomina.
    assert set(by_id) == {"Task_A", "Task_B", "Task_C"}


def test_a_v1_run_keeps_its_model_with_only_the_consultant_choices_as_manual(client, monkeypatch):
    _capture_engine(monkeypatch)
    created = client.post(
        f"/v1/workspace/bpmn-models/{_bpmn_model_id(client)}/simulation-runs",
        json={
            "total_cases": 5,
            "current_bpmn_xml": MINIMAL_BPMN,
            "default_task_duration_seconds": 900,
            "tasks": [
                {"element_id": "Task_A", "mean_seconds": 1500, "distribution": "gamma", "std_seconds": 300},
                {"element_id": "Task_B", "mean_seconds": 900},
            ],
        },
    )
    assert created.status_code == 200, created.text

    model = _model_of(client, created.json()["id"])

    by_id = {activity["element_id"]: activity["assignments"][0] for activity in model["activities"]}
    assert by_id["Task_A"]["duration"]["kind"] == "gamma"
    assert by_id["Task_A"]["provenance"]["origin"] == "manual"
    assert by_id["Task_B"]["provenance"] is None


def test_a_run_from_before_the_model_was_kept_says_so(client, monkeypatch):
    from backend.workspace_storage import WorkspaceSimulationRun, workspace_connection

    _capture_engine(monkeypatch)
    created = client.post(
        f"/v1/workspace/bpmn-models/{_bpmn_model_id(client)}/simulation-runs",
        json={"total_cases": 5, "current_bpmn_xml": MINIMAL_BPMN},
    )
    run_id = created.json()["id"]
    with workspace_connection() as session:
        session.get(WorkspaceSimulationRun, run_id).model_json = None

    assert _model_of(client, run_id) is None


def test_an_unknown_run_has_no_model(client):
    response = client.get("/v1/workspace/simulation-runs/987654321/model")

    assert response.status_code == 404
