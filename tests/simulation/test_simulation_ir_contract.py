"""SIM-37: il contratto di run sull'IR - patch, baseline, validazione sul BPMN, API."""

import pytest
from pydantic import ValidationError

from backend.simulation.ir.model import (
    Activity,
    Arrival,
    Assignment,
    Branch,
    Calendar,
    CalendarPeriod,
    CaseAttribute,
    Condition,
    DiscreteOption,
    Exponential,
    Gateway,
    LogNormal,
    Normal,
    Resource,
    ResourcePool,
    Rule,
    SimulationModel,
)
from backend.simulation.ir.patch import ModelPatch, apply_patch

OFFICE = Calendar(
    id="office",
    name="Ufficio",
    periods=(CalendarPeriod(from_day="MONDAY", to_day="FRIDAY", begin="09:00:00", end="17:00:00"),),
)
NIGHT = Calendar(
    id="night",
    name="Notte",
    periods=(
        CalendarPeriod(from_day="MONDAY", to_day="FRIDAY", begin="22:00:00", end="23:59:59"),
        CalendarPeriod(from_day="TUESDAY", to_day="SATURDAY", begin="00:00:00", end="06:00:00"),
    ),
)


def _when(attribute, operator, value) -> Condition:
    return Condition(any_of=((Rule(attribute=attribute, operator=operator, value=value),),))


def _baseline() -> SimulationModel:
    return SimulationModel(
        arrival=Arrival(interarrival=Exponential(mean=1800, minimum=0, maximum=18000), calendar_id="office"),
        calendars=(OFFICE,),
        pools=(
            ResourcePool(
                id="p",
                name="Ufficio",
                resources=(Resource(id="ops", name="Operatore", cost_per_hour=30, amount=2, calendar_id="office"),),
            ),
        ),
        activities=(
            Activity(element_id="Task_A", assignments=(
                Assignment(resource_id="ops", duration=Normal(mean=600, std=60, minimum=420, maximum=780)),)),
            Activity(element_id="Task_B", assignments=(
                Assignment(resource_id="ops", duration=Normal(mean=900, std=90, minimum=630, maximum=1170)),)),
        ),
        gateways=(
            Gateway(element_id="Gateway_1", branches=(
                Branch(flow_id="Flow_3", probability=0.5),
                Branch(flow_id="Flow_4", probability=0.5),
            )),
        ),
    )


# --------------------------------------------------------------------------- #
# Patch sulla baseline
# --------------------------------------------------------------------------- #


def test_an_empty_patch_gives_back_the_baseline():
    assert apply_patch(_baseline(), ModelPatch()) == _baseline()


def test_a_patch_replaces_by_id_and_keeps_the_rest_in_order():
    approvers = ResourcePool(id="p", name="Ufficio", resources=(
        Resource(id="ops", name="Operatore", cost_per_hour=30, amount=3, calendar_id="office"),))
    slower_b = Activity(element_id="Task_B", assignments=(
        Assignment(resource_id="ops", duration=LogNormal(mean=900, variance=40000, minimum=60, maximum=5400)),))

    patched = apply_patch(_baseline(), ModelPatch(pools=(approvers,), activities=(slower_b,)))

    assert patched.resources()["ops"].amount == 3
    assert [a.element_id for a in patched.activities] == ["Task_A", "Task_B"]
    assert patched.activities[0] == _baseline().activities[0]
    assert isinstance(patched.activities[1].assignments[0].duration, LogNormal)


def test_a_patch_adds_what_the_baseline_did_not_have():
    night_shift = ResourcePool(id="night-pool", name="Turno di notte", resources=(
        Resource(id="night-ops", name="Operatore notte", cost_per_hour=40, amount=1, calendar_id="night"),))

    patched = apply_patch(_baseline(), ModelPatch(calendars=(NIGHT,), pools=(night_shift,)))

    assert [c.id for c in patched.calendars] == ["office", "night"]
    assert patched.resources()["night-ops"].calendar_id == "night"


def test_sections_without_ids_are_replaced_whole():
    size = CaseAttribute(name="importo", options=(
        DiscreteOption(value="1000", probability=0.7), DiscreteOption(value="9000", probability=0.3)))
    routed = Gateway(element_id="Gateway_1", branches=(
        Branch(flow_id="Flow_3", probability=0.5, condition=_when("importo", ">", 5000)),
        Branch(flow_id="Flow_4", probability=0.5, condition=_when("importo", "<=", 5000)),
    ))

    patched = apply_patch(_baseline(), ModelPatch(case_attributes=(size,), gateways=(routed,)))

    assert patched.case_attributes == (size,)
    assert patched.gateways[0].branches[0].condition is not None


def test_a_patch_that_breaks_a_reference_is_refused():
    orphan = Activity(element_id="Task_A", assignments=(
        Assignment(resource_id="nobody", duration=Normal(mean=600, std=60, minimum=420, maximum=780)),))

    with pytest.raises(ValidationError, match="risorsa sconosciuta nobody"):
        apply_patch(_baseline(), ModelPatch(activities=(orphan,)))


def test_a_patch_with_the_same_id_twice_is_refused():
    with pytest.raises(ValidationError, match="calendario nella patch duplicato: office"):
        ModelPatch(calendars=(OFFICE, OFFICE))


# --------------------------------------------------------------------------- #
# Baseline e verifica sul BPMN
# --------------------------------------------------------------------------- #

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

LANES_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">
  <bpmn:collaboration id="Collab_1">
    <bpmn:participant id="Pool_1" name="Ufficio acquisti" processRef="Process_1" />
  </bpmn:collaboration>
  <bpmn:process id="Process_1" isExecutable="false">
    <bpmn:laneSet id="LaneSet_1">
      <bpmn:lane id="Lane_Ops" name="Operatori"><bpmn:flowNodeRef>Task_A</bpmn:flowNodeRef></bpmn:lane>
      <bpmn:lane id="Lane_Boss" name="Responsabili"><bpmn:flowNodeRef>Task_B</bpmn:flowNodeRef></bpmn:lane>
    </bpmn:laneSet>
    <bpmn:startEvent id="StartEvent_1" />
    <bpmn:task id="Task_A" name="Prepara" />
    <bpmn:task id="Task_B" name="Approva" />
    <bpmn:endEvent id="EndEvent_1" />
    <bpmn:sequenceFlow id="Flow_1" sourceRef="StartEvent_1" targetRef="Task_A" />
    <bpmn:sequenceFlow id="Flow_2" sourceRef="Task_A" targetRef="Task_B" />
    <bpmn:sequenceFlow id="Flow_3" sourceRef="Task_B" targetRef="EndEvent_1" />
  </bpmn:process>
</bpmn:definitions>
"""


def test_the_baseline_covers_every_task_and_gateway_and_declares_no_source():
    from backend.simulation.ir.from_request import DEFAULT_RESOURCE_ID
    from backend.simulation.scenario_builder import baseline_for_bpmn

    model = baseline_for_bpmn(MINIMAL_BPMN)

    assert [a.element_id for a in model.activities] == ["Task_A", "Task_B", "Task_C"]
    assert [b.probability for b in model.gateways[0].branches] == [0.5, 0.5]
    assert list(model.resources()) == [DEFAULT_RESOURCE_ID]
    # Nessun numero della baseline viene da una fonte: sono assunzioni.
    assert model.arrival.provenance is None
    assert all(a.assignments[0].provenance is None for a in model.activities)


def test_the_baseline_gives_each_lane_its_tasks():
    from backend.simulation.scenario_builder import baseline_for_bpmn

    model = baseline_for_bpmn(LANES_BPMN)

    names = {r.id: r.name for r in model.resources().values()}
    owner = {a.element_id: names[a.assignments[0].resource_id] for a in model.activities}
    assert owner == {"Task_A": "Operatori", "Task_B": "Responsabili"}


def test_the_baseline_compiles_like_the_default_v1_request():
    # Stesso BPMN, nessuna configurazione: v2 e v1 mandano al motore lo stesso
    # scenario. Cambia solo la provenienza, che il motore non vede.
    from backend.schemas.simulation import CreateSimulationRunRequest
    from backend.simulation.scenario_builder import (
        baseline_for_bpmn,
        build_prosimos_scenario,
        build_prosimos_scenario_from_model,
    )

    v1 = build_prosimos_scenario(bpmn_xml=MINIMAL_BPMN, request=CreateSimulationRunRequest())
    v2 = build_prosimos_scenario_from_model(bpmn_xml=MINIMAL_BPMN, model=baseline_for_bpmn(MINIMAL_BPMN))
    assert v2.payload == v1.payload


def _drop_task_c(model):
    return model.model_copy(update={"activities": model.activities[:2]})


def _add_task_x(model):
    extra = model.activities[0].model_copy(update={"element_id": "Task_X"})
    return model.model_copy(update={"activities": (*model.activities, extra)})


def _drop_gateways(model):
    return model.model_copy(update={"gateways": ()})


def _wrong_flow(model):
    gateway = Gateway(element_id="Gateway_1", branches=(
        Branch(flow_id="Flow_3", probability=0.5), Branch(flow_id="Flow_9", probability=0.5)))
    return model.model_copy(update={"gateways": (gateway,)})


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (_drop_task_c, "task del BPMN senza parametri: Task_C"),
        (_add_task_x, "attivita' che il BPMN non ha: Task_X"),
        (_drop_gateways, "gateway del BPMN senza rami: Gateway_1"),
        (_wrong_flow, "rami che il BPMN non ha: Flow_9"),
    ],
)
def test_a_model_that_does_not_match_the_bpmn_is_refused_before_the_engine(change, message):
    from backend.simulation.scenario_builder import baseline_for_bpmn, build_prosimos_scenario_from_model

    with pytest.raises(ValueError, match=message):
        build_prosimos_scenario_from_model(bpmn_xml=MINIMAL_BPMN, model=change(baseline_for_bpmn(MINIMAL_BPMN)))


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from backend.app import app

    with TestClient(app) as test_client:
        yield test_client


def _bpmn_model_id(client) -> str:
    client_id = client.post("/v1/workspace/clients", json={"name": "SIM-37 Client"}).json()["id"]
    project_id = client.post(
        "/v1/workspace/projects", json={"client_id": client_id, "name": "SIM-37 Project"}
    ).json()["id"]
    process = client.post(f"/v1/workspace/projects/{project_id}/processes", json={"name": "SIM-37 Process"})
    assert process.status_code == 200
    return process.json()["bpmn_model_id"]


def _capture_engine(monkeypatch) -> list:
    from backend.simulation.models import ProsimosSimulationResult

    sent: list = []

    async def fake_engine(request):
        sent.append(request)
        return ProsimosSimulationResult(payload={"statsFile": "s.csv", "logFile": "e.csv"})

    monkeypatch.setattr("backend.simulation.service.run_prosimos_simulation", fake_engine)
    return sent


def _runs_url(bpmn_model_id: str) -> str:
    return f"/v1/workspace/bpmn-models/{bpmn_model_id}/simulation-model-runs"


def test_the_api_gives_back_the_baseline_ir_of_the_process(client):
    bpmn_model_id = _bpmn_model_id(client)

    response = client.post(
        f"/v1/workspace/bpmn-models/{bpmn_model_id}/simulation-model",
        json={"current_bpmn_xml": MINIMAL_BPMN},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["bpmn_model_id"] == bpmn_model_id
    assert [a["element_id"] for a in body["model"]["activities"]] == ["Task_A", "Task_B", "Task_C"]
    assert body["model"]["activities"][0]["assignments"][0]["duration"]["kind"] == "normal"
    # Quello che l'API restituisce torna indietro come modello valido.
    assert SimulationModel.model_validate(body["model"])


def test_the_api_without_a_bpmn_says_what_to_do(client):
    response = client.post(f"/v1/workspace/bpmn-models/{_bpmn_model_id(client)}/simulation-model", json={})

    assert response.status_code == 400
    assert "BPMN" in response.json()["error"]["message"]


def test_a_patch_with_calendars_lognormal_and_rules_reaches_the_engine(client, monkeypatch):
    from backend.simulation.ir.from_request import DEFAULT_POOL_ID, STANDARD_CALENDAR_ID

    sent = _capture_engine(monkeypatch)
    bpmn_model_id = _bpmn_model_id(client)
    patch = ModelPatch(
        calendars=(NIGHT,),
        pools=(ResourcePool(id=DEFAULT_POOL_ID, name="Ufficio", resources=(
            Resource(id="ops", name="Operatore", cost_per_hour=30, amount=2, calendar_id=STANDARD_CALENDAR_ID),
            Resource(id="night-ops", name="Notturno", cost_per_hour=45, amount=1, calendar_id="night"),
        )),),
        activities=(
            Activity(element_id="Task_A", assignments=(
                Assignment(resource_id="ops", duration=LogNormal(mean=600, variance=90000, minimum=60, maximum=3600)),
            )),
            Activity(element_id="Task_B", assignments=(
                Assignment(resource_id="night-ops", duration=Normal(mean=900, std=90, minimum=630, maximum=1170)),
            )),
            Activity(element_id="Task_C", assignments=(
                Assignment(resource_id="ops", duration=Normal(mean=300, std=30, minimum=210, maximum=390)),
            )),
        ),
        gateways=(Gateway(element_id="Gateway_1", branches=(
            Branch(flow_id="Flow_3", probability=0.5, condition=_when("importo", ">", 5000)),
            Branch(flow_id="Flow_4", probability=0.5, condition=_when("importo", "<=", 5000)),
        )),),
        case_attributes=(CaseAttribute(name="importo", options=(
            DiscreteOption(value="1000", probability=0.6), DiscreteOption(value="9000", probability=0.4))),),
    )

    response = client.post(
        _runs_url(bpmn_model_id),
        json={
            "scenario_name": "Turno di notte",
            "total_cases": 20,
            "seed": 11,
            "current_bpmn_xml": MINIMAL_BPMN,
            "patch": patch.model_dump(mode="json"),
        },
    )

    assert response.status_code == 200, response.text
    run = client.get(f"/v1/workspace/simulation-runs/{response.json()['id']}").json()
    assert run["status"] == "completed"
    assert run["scenario_name"] == "Turno di notte"
    assert run["request"]["patch"]["calendars"][0]["id"] == "night"
    assert "current_bpmn_xml" not in run["request"] or run["request"]["current_bpmn_xml"] is None
    [engine_request] = sent
    payload = engine_request.scenario.payload
    assert engine_request.seed == 11
    assert engine_request.total_cases == 20
    durations = {t["task_id"]: t["resources"][0]["distribution_name"] for t in payload["task_resource_distribution"]}
    assert durations["Task_A"] == "lognorm"
    assert {c["id"] for c in payload["resource_calendars"]} == {STANDARD_CALENDAR_ID, "night"}
    assert {rule["id"] for rule in payload["branch_rules"]} == {"Gateway_1::Flow_3", "Gateway_1::Flow_4"}
    assert payload["case_attributes"][0]["name"] == "importo"


def test_a_full_model_runs_and_gets_an_idempotency_key(client, monkeypatch):
    from backend.simulation.scenario_builder import baseline_for_bpmn

    sent = _capture_engine(monkeypatch)
    body = {
        "total_cases": 5,
        "current_bpmn_xml": MINIMAL_BPMN,
        "model": baseline_for_bpmn(MINIMAL_BPMN).model_dump(mode="json"),
    }

    response = client.post(_runs_url(_bpmn_model_id(client)), json=body)

    assert response.status_code == 200, response.text
    assert response.json()["idempotency_key"]
    assert len(sent) == 1


def test_the_same_ir_request_in_flight_is_not_run_twice(client, monkeypatch):
    # Il primo run resta "pending": il motore non viene lanciato in background.
    monkeypatch.setattr("backend.api.routes.simulation.execute_simulation_run", lambda **_: None)
    bpmn_model_id = _bpmn_model_id(client)
    body = {"total_cases": 5, "seed": 3, "current_bpmn_xml": MINIMAL_BPMN, "patch": {}}

    first = client.post(_runs_url(bpmn_model_id), json=body)
    second = client.post(_runs_url(bpmn_model_id), json={**body, "patch": None})

    assert first.status_code == second.status_code == 200
    # Patch vuota e nessuna patch arrivano allo stesso scenario: e' lo stesso run.
    assert first.json()["id"] == second.json()["id"]


@pytest.mark.parametrize(
    ("extra", "status", "message"),
    [
        (
            {"patch": {"activities": [{"element_id": "Task_A", "assignments": [
                {"resource_id": "nobody", "duration": {"kind": "fixed", "value": 60}}]}]}},
            400,
            "risorsa sconosciuta",
        ),
        (
            {"patch": {"activities": [{"element_id": "Task_Z", "assignments": [
                {"resource_id": "delir-resource-operator", "duration": {"kind": "fixed", "value": 60}}]}]}},
            400,
            "attivita' che il BPMN non ha: Task_Z",
        ),
        ({"patch": {"arrival": {"interarrival": {"kind": "triangular"}, "calendar_id": "x"}}}, 422, ""),
        ({"patch": {}, "model": _baseline().model_dump(mode="json")}, 422, "non entrambi"),
    ],
)
def test_the_api_refuses_what_it_cannot_simulate_without_creating_a_run(client, monkeypatch, extra, status, message):
    from unittest.mock import Mock

    engine = Mock(side_effect=AssertionError("Un modello non valido e' arrivato al motore"))
    monkeypatch.setattr("backend.simulation.service.run_prosimos_simulation", engine)
    bpmn_model_id = _bpmn_model_id(client)

    response = client.post(_runs_url(bpmn_model_id), json={"current_bpmn_xml": MINIMAL_BPMN, **extra})

    assert response.status_code == status, response.text
    assert message in str(response.json()["error"])
    assert client.get(f"/v1/workspace/bpmn-models/{bpmn_model_id}/simulation-runs").json() == []
