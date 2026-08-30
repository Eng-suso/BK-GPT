import xml.etree.ElementTree as ElementTree

import pytest
from fastapi.testclient import TestClient

from backend.schemas.simulation import CreateSimulationRunRequest
from backend.simulation.bpmn_normalizer import normalize_bpmn_for_prosimos
from backend.simulation.models import ProsimosSimulationResult
from backend.simulation.scenario_builder import build_prosimos_scenario


MINIMAL_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">
  <bpmn:process id="Process_1" isExecutable="false">
    <bpmn:startEvent id="StartEvent_1" />
    <bpmn:task id="Task_A" name="Ricevi richiesta" />
    <bpmn:exclusiveGateway id="Gateway_1" />
    <bpmn:task id="Task_B" name="Approva" />
    <bpmn:task id="Task_C" name="Rifiuta" />
    <bpmn:endEvent id="EndEvent_1" />
    <bpmn:sequenceFlow id="Flow_1" sourceRef="StartEvent_1" targetRef="Task_A" />
    <bpmn:sequenceFlow id="Flow_2" sourceRef="Task_A" targetRef="Gateway_1" />
    <bpmn:sequenceFlow id="Flow_3" sourceRef="Gateway_1" targetRef="Task_B" />
    <bpmn:sequenceFlow id="Flow_4" sourceRef="Gateway_1" targetRef="Task_C" />
    <bpmn:sequenceFlow id="Flow_5" sourceRef="Task_B" targetRef="EndEvent_1" />
    <bpmn:sequenceFlow id="Flow_6" sourceRef="Task_C" targetRef="EndEvent_1" />
  </bpmn:process>
</bpmn:definitions>
"""


MULTI_END_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">
  <bpmn:process id="Process_1" isExecutable="false">
    <bpmn:startEvent id="Start_1" />
    <bpmn:task id="Task_A" name="Ricevi" />
    <bpmn:exclusiveGateway id="Gw_1" />
    <bpmn:task id="Task_B" name="Approva" />
    <bpmn:task id="Task_C" name="Rifiuta" />
    <bpmn:endEvent id="End_OK" />
    <bpmn:endEvent id="End_KO" />
    <bpmn:sequenceFlow id="F1" sourceRef="Start_1" targetRef="Task_A" />
    <bpmn:sequenceFlow id="F2" sourceRef="Task_A" targetRef="Gw_1" />
    <bpmn:sequenceFlow id="F3" sourceRef="Gw_1" targetRef="Task_B" />
    <bpmn:sequenceFlow id="F4" sourceRef="Gw_1" targetRef="Task_C" />
    <bpmn:sequenceFlow id="F5" sourceRef="Task_B" targetRef="End_OK" />
    <bpmn:sequenceFlow id="F6" sourceRef="Task_C" targetRef="End_KO" />
  </bpmn:process>
</bpmn:definitions>
"""

_BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"


def test_normalize_bpmn_collapses_multiple_end_events():
    normalized = normalize_bpmn_for_prosimos(MULTI_END_BPMN)
    root = ElementTree.fromstring(normalized)

    end_events = root.findall(f".//{{{_BPMN_NS}}}endEvent")
    assert len(end_events) == 1
    survivor_id = end_events[0].get("id")

    targets = {
        flow.get("targetRef")
        for flow in root.findall(f".//{{{_BPMN_NS}}}sequenceFlow")
    }
    # Every flow that used to hit End_KO now points at the survivor.
    assert "End_KO" not in targets
    assert survivor_id in targets


def test_normalize_bpmn_is_noop_for_single_end_event():
    assert normalize_bpmn_for_prosimos(MINIMAL_BPMN) == MINIMAL_BPMN


@pytest.fixture()
def client():
    from backend.app import app

    with TestClient(app) as test_client:
        yield test_client


def test_build_prosimos_scenario_from_bpmn():
    scenario = build_prosimos_scenario(
        bpmn_xml=MINIMAL_BPMN,
        request=CreateSimulationRunRequest(
            total_cases=25,
            arrival_interval_seconds=600,
            default_task_duration_seconds=300,
            default_cost_per_hour=40,
            resource_amount=2,
            resource_name="Back office",
        ),
    )

    payload = scenario.payload
    assert scenario.task_count == 3
    assert scenario.gateway_count == 1
    assert payload["resource_profiles"][0]["resource_list"][0]["assignedTasks"] == [
        "Task_A",
        "Task_B",
        "Task_C",
    ]
    assert payload["task_resource_distribution"][0]["resources"][0]["distribution_name"] == "norm"
    assert payload["gateway_branching_probabilities"][0]["probabilities"] == [
        {"path_id": "Flow_3", "value": "0.5"},
        {"path_id": "Flow_4", "value": "0.5"},
    ]


def test_simulation_endpoint_uses_prosimos_adapter_contract(client, monkeypatch):
    async def fake_run_prosimos_simulation(request):
        assert request.scenario.task_count == 3
        assert request.total_cases == 10
        return ProsimosSimulationResult(
            payload={"statsFile": "stats_test.csv", "logFile": "events_test.csv"},
        )

    monkeypatch.setattr(
        "backend.simulation.service.run_prosimos_simulation",
        fake_run_prosimos_simulation,
    )

    client_payload = client.post("/v1/workspace/clients", json={"name": "Simulation Test Client"})
    assert client_payload.status_code == 200
    project_payload = client.post(
        "/v1/workspace/projects",
        json={"client_id": client_payload.json()["id"], "name": "Simulation Test Project"},
    )
    assert project_payload.status_code == 200
    process_payload = client.post(
        f"/v1/workspace/projects/{project_payload.json()['id']}/processes",
        json={"name": "Simulation Test Process"},
    )
    assert process_payload.status_code == 200

    bpmn_model_id = process_payload.json()["bpmn_model_id"]
    response = client.post(
        f"/v1/workspace/bpmn-models/{bpmn_model_id}/simulation-runs",
        json={
            "scenario_name": "Mocked Prosimos",
            "total_cases": 10,
            "current_bpmn_xml": MINIMAL_BPMN,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["engine"] == "prosimos"
    # The run is launched in the background; TestClient drains background tasks
    # before returning, so by now the stored run is finished.
    run_id = body["id"]
    finished = client.get(f"/v1/workspace/simulation-runs/{run_id}")
    assert finished.status_code == 200
    finished_body = finished.json()
    assert finished_body["status"] == "completed"
    assert finished_body["outputs"] == ["stats_test.csv", "events_test.csv"]


def test_prepare_simulation_run_dedupes_in_flight_runs(client):
    from backend.schemas.workspace import BpmnModelResponse
    from backend.simulation.service import prepare_simulation_run

    client_payload = client.post("/v1/workspace/clients", json={"name": "Idem Client"})
    project_payload = client.post(
        "/v1/workspace/projects",
        json={"client_id": client_payload.json()["id"], "name": "Idem Project"},
    )
    process_payload = client.post(
        f"/v1/workspace/projects/{project_payload.json()['id']}/processes",
        json={"name": "Idem Process"},
    )
    bpmn_model_id = process_payload.json()["bpmn_model_id"]

    model = BpmnModelResponse(
        id=bpmn_model_id,
        process_id=process_payload.json()["id"],
        name="Idem Process",
        xml=MINIMAL_BPMN,
    )
    request = CreateSimulationRunRequest(
        total_cases=10,
        current_bpmn_xml=MINIMAL_BPMN,
        idempotency_key="fixed-key-123",
    )

    first_run, first_scenario, _ = prepare_simulation_run(bpmn_model=model, request=request)
    second_run, second_scenario, _ = prepare_simulation_run(bpmn_model=model, request=request)

    assert first_scenario is not None
    # Same key, first run still pending -> reuse, no execution.
    assert second_scenario is None
    assert second_run["id"] == first_run["id"]
