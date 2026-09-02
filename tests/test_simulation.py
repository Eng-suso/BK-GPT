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


def test_normalize_bpmn_maps_every_element_to_prosimos_vocabulary():
    bpmn = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">
  <bpmn:process id="Process_1" isExecutable="false">
    <bpmn:laneSet id="ls"><bpmn:lane id="l1"><bpmn:flowNodeRef>T_U</bpmn:flowNodeRef></bpmn:lane></bpmn:laneSet>
    <bpmn:startEvent id="S1"><bpmn:outgoing>f1</bpmn:outgoing></bpmn:startEvent>
    <bpmn:startEvent id="S2"><bpmn:outgoing>f1b</bpmn:outgoing></bpmn:startEvent>
    <bpmn:userTask id="T_U"><bpmn:incoming>f1</bpmn:incoming><bpmn:incoming>f1b</bpmn:incoming><bpmn:outgoing>f2</bpmn:outgoing></bpmn:userTask>
    <bpmn:intermediateCatchEvent id="IC"><bpmn:timerEventDefinition/><bpmn:incoming>f2</bpmn:incoming><bpmn:outgoing>f3</bpmn:outgoing></bpmn:intermediateCatchEvent>
    <bpmn:subProcess id="SP"><bpmn:incoming>f3</bpmn:incoming><bpmn:outgoing>f4</bpmn:outgoing>
      <bpmn:startEvent id="sp_s"/><bpmn:task id="sp_t"/><bpmn:endEvent id="sp_e"/>
    </bpmn:subProcess>
    <bpmn:endEvent id="E1"><bpmn:incoming>f4</bpmn:incoming></bpmn:endEvent>
    <bpmn:endEvent id="E2"><bpmn:incoming>f5</bpmn:incoming></bpmn:endEvent>
    <bpmn:sequenceFlow id="f1" sourceRef="S1" targetRef="T_U"/>
    <bpmn:sequenceFlow id="f1b" sourceRef="S2" targetRef="T_U"/>
    <bpmn:sequenceFlow id="f2" sourceRef="T_U" targetRef="IC"/>
    <bpmn:sequenceFlow id="f3" sourceRef="IC" targetRef="SP"/>
    <bpmn:sequenceFlow id="f4" sourceRef="SP" targetRef="E1"/>
    <bpmn:sequenceFlow id="f5" sourceRef="T_U" targetRef="E2"/>
  </bpmn:process>
</bpmn:definitions>
"""
    root = ElementTree.fromstring(normalize_bpmn_for_prosimos(bpmn))

    def tags(name: str) -> list:
        return root.findall(f".//{{{_BPMN_NS}}}{name}")

    supported = {
        "task",
        "startEvent",
        "endEvent",
        "exclusiveGateway",
        "parallelGateway",
        "inclusiveGateway",
        "eventBasedGateway",
        "sequenceFlow",
        "process",
        "definitions",
        "incoming",
        "outgoing",
    }
    seen = {_BPMN_NS and el.tag.rsplit("}", 1)[-1] for el in root.iter()}
    assert seen <= supported, seen - supported

    assert len(tags("startEvent")) == 1
    assert len(tags("endEvent")) == 1
    assert tags("laneSet") == []
    assert tags("subProcess") == []
    assert tags("intermediateCatchEvent") == []
    # IC spliced: T_U now flows straight into the sub-process (now a task).
    assert {"sp_s", "sp_t", "sp_e"}.isdisjoint(
        {el.get("id") for el in root.iter()}
    )


def test_normalize_bpmn_downcasts_activities_and_drops_boundary_events():
    bpmn = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">
  <bpmn:process id="Process_1" isExecutable="false">
    <bpmn:startEvent id="Start_1" />
    <bpmn:userTask id="Task_U" name="Verifica" />
    <bpmn:serviceTask id="Task_S" name="Notifica" />
    <bpmn:boundaryEvent id="Boundary_1" attachedToRef="Task_U" />
    <bpmn:endEvent id="End_1" />
    <bpmn:sequenceFlow id="F1" sourceRef="Start_1" targetRef="Task_U" />
    <bpmn:sequenceFlow id="F2" sourceRef="Task_U" targetRef="Task_S" />
    <bpmn:sequenceFlow id="F3" sourceRef="Task_S" targetRef="End_1" />
    <bpmn:sequenceFlow id="F_err" sourceRef="Boundary_1" targetRef="End_1" />
  </bpmn:process>
</bpmn:definitions>
"""
    root = ElementTree.fromstring(normalize_bpmn_for_prosimos(bpmn))

    assert root.findall(f".//{{{_BPMN_NS}}}userTask") == []
    assert root.findall(f".//{{{_BPMN_NS}}}serviceTask") == []
    assert len(root.findall(f".//{{{_BPMN_NS}}}task")) == 2
    assert root.findall(f".//{{{_BPMN_NS}}}boundaryEvent") == []
    flow_ids = {f.get("id") for f in root.findall(f".//{{{_BPMN_NS}}}sequenceFlow")}
    assert "F_err" not in flow_ids
    assert {"F1", "F2", "F3"} <= flow_ids


def test_normalize_bpmn_drops_orphaned_exception_handler_subtree():
    bpmn = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">
  <bpmn:process id="Process_1" isExecutable="false">
    <bpmn:startEvent id="Start_1" />
    <bpmn:userTask id="Task_U" name="Attendi" />
    <bpmn:endEvent id="End_1" />
    <bpmn:boundaryEvent id="Boundary_1" attachedToRef="Task_U" />
    <bpmn:task id="Task_Handler" name="Gestisci errore" />
    <bpmn:endEvent id="End_Handler" />
    <bpmn:sequenceFlow id="F1" sourceRef="Start_1" targetRef="Task_U" />
    <bpmn:sequenceFlow id="F2" sourceRef="Task_U" targetRef="End_1" />
    <bpmn:sequenceFlow id="F_bnd" sourceRef="Boundary_1" targetRef="Task_Handler" />
    <bpmn:sequenceFlow id="F_h" sourceRef="Task_Handler" targetRef="End_Handler" />
  </bpmn:process>
</bpmn:definitions>
"""
    root = ElementTree.fromstring(normalize_bpmn_for_prosimos(bpmn))

    task_ids = {t.get("id") for t in root.findall(f".//{{{_BPMN_NS}}}task")}
    assert "Task_Handler" not in task_ids
    end_ids = {e.get("id") for e in root.findall(f".//{{{_BPMN_NS}}}endEvent")}
    assert "End_Handler" not in end_ids
    flow_ids = {f.get("id") for f in root.findall(f".//{{{_BPMN_NS}}}sequenceFlow")}
    assert flow_ids == {"F1", "F2"}


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


def test_build_prosimos_scenario_applies_per_element_overrides():
    from backend.schemas.simulation import (
        SimGatewayBranchConfig,
        SimGatewayConfig,
        SimResourceConfig,
        SimTaskConfig,
    )

    scenario = build_prosimos_scenario(
        bpmn_xml=MINIMAL_BPMN,
        request=CreateSimulationRunRequest(
            resources=[
                SimResourceConfig(id="r_front", name="Front", cost_per_hour=30, amount=2),
                SimResourceConfig(id="r_back", name="Back", cost_per_hour=45, amount=1),
            ],
            tasks=[
                SimTaskConfig(element_id="Task_A", mean_seconds=1200, distribution="fixed", resource_id="r_front"),
                SimTaskConfig(element_id="Task_B", mean_seconds=600, resource_id="r_back"),
            ],
            gateways=[
                SimGatewayConfig(
                    element_id="Gateway_1",
                    branches=[
                        SimGatewayBranchConfig(flow_id="Flow_3", probability=0.7),
                        SimGatewayBranchConfig(flow_id="Flow_4", probability=0.3),
                    ],
                )
            ],
        ),
    )
    payload = scenario.payload

    pool = payload["resource_profiles"][0]["resource_list"]
    by_id = {r["id"]: r for r in pool}
    assert "Task_A" in by_id["r_front"]["assignedTasks"]
    assert by_id["r_back"]["assignedTasks"] == ["Task_B"]
    # Task_C had no config → falls to the first resource.
    assert "Task_C" in by_id["r_front"]["assignedTasks"]

    dist = {d["task_id"]: d["resources"][0] for d in payload["task_resource_distribution"]}
    assert dist["Task_A"]["distribution_name"] == "fix"
    assert dist["Task_A"]["distribution_params"][0]["value"] == 1200
    assert dist["Task_A"]["resource_id"] == "r_front"
    assert dist["Task_B"]["resource_id"] == "r_back"

    probs = payload["gateway_branching_probabilities"][0]["probabilities"]
    assert [p["value"] for p in probs] == ["0.7", "0.3"]


def test_describe_scenario_template_lists_tasks_and_branches():
    from backend.simulation.scenario_builder import describe_scenario_template

    template = describe_scenario_template(MINIMAL_BPMN)
    task_ids = {t.element_id for t in template.tasks}
    assert {"Task_A", "Task_B", "Task_C"} <= task_ids
    assert len(template.gateways) == 1
    gateway = template.gateways[0]
    assert gateway.element_id == "Gateway_1"
    assert {b.flow_id for b in gateway.branches} == {"Flow_3", "Flow_4"}
    assert {b.target_name for b in gateway.branches} == {"Approva", "Rifiuta"}


def test_scenario_template_endpoint(client):
    client_payload = client.post("/v1/workspace/clients", json={"name": "Tmpl Client"})
    project_payload = client.post(
        "/v1/workspace/projects",
        json={"client_id": client_payload.json()["id"], "name": "Tmpl Project"},
    )
    process_payload = client.post(
        f"/v1/workspace/projects/{project_payload.json()['id']}/processes",
        json={"name": "Tmpl Process"},
    )
    bpmn_model_id = process_payload.json()["bpmn_model_id"]

    response = client.post(
        f"/v1/workspace/bpmn-models/{bpmn_model_id}/simulation-template",
        json={"current_bpmn_xml": MINIMAL_BPMN},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["tasks"]) == 3
    assert body["gateways"][0]["element_id"] == "Gateway_1"


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
