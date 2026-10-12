import asyncio
from unittest.mock import Mock
from xml.etree import ElementTree

import pytest

from backend.schemas.simulation import CreateSimulationRunRequest
from backend.schemas.workspace import BpmnModelResponse
from backend.simulation.bpmn_normalizer import normalize_bpmn_for_prosimos
from backend.simulation.models import ProsimosScenario, ProsimosSimulationRequest
from backend.simulation.prosimos_adapter import ProsimosError, run_prosimos_simulation
from backend.simulation.service import prepare_simulation_run
from backend.simulation.validation import validate_simulation_bpmn


NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
NODES = '<startEvent id="S"/><task id="T"/><endEvent id="E"/>'
FLOWS = '<sequenceFlow id="F1" sourceRef="S" targetRef="T"/><sequenceFlow id="F2" sourceRef="T" targetRef="E"/>'


def model(body=NODES + FLOWS, extra=""):
    return f'<definitions xmlns="{NS}"><process id="P">{body}</process>{extra}</definitions>'


@pytest.mark.parametrize(
    "xml, message",
    [
        (
            model(NODES.replace('<endEvent id="E"/>', "") + FLOWS),
            "Manca un evento di fine",
        ),
        (
            model(NODES.replace('<startEvent id="S"/>', "") + FLOWS),
            "Manca un evento di inizio",
        ),
        (
            model(NODES + '<sequenceFlow id="F1" sourceRef="S" targetRef="T"/>'),
            "Nessun evento di fine",
        ),
        (
            model(NODES + FLOWS.replace('targetRef="E"', 'targetRef="Missing"')),
            "nodo inesistente",
        ),
        (model(NODES + FLOWS + '<task id="Orphan"/>'), "Nodi scollegati"),
        (
            model(
                NODES
                + FLOWS
                + '<task id="Dead"/><sequenceFlow id="F3" sourceRef="T" targetRef="Dead"/>'
            ),
            "Rami senza percorso",
        ),
        (
            model(
                NODES
                + FLOWS
                + '<task id="Loop"/><sequenceFlow id="F3" sourceRef="T" targetRef="Loop"/><sequenceFlow id="F4" sourceRef="Loop" targetRef="Loop"/>'
            ),
            "Rami senza percorso",
        ),
        (model(NODES + FLOWS + '<task id="T"/>'), "ID duplicato"),
        (
            model(
                NODES + FLOWS + '<sequenceFlow id="F3" sourceRef="E" targetRef="T"/>'
            ),
            "evento di fine ha uscite",
        ),
        ("<definitions/>", "namespace BPMN"),
        ("<broken", "XML BPMN non valido"),
    ],
)
def test_invalid_models_are_rejected(xml, message):
    with pytest.raises(ValueError, match=message):
        validate_simulation_bpmn(normalize_bpmn_for_prosimos(xml))


def test_disconnected_end_is_preserved_for_diagnosis():
    xml = model(NODES + '<sequenceFlow id="F1" sourceRef="S" targetRef="T"/>')
    normalized = normalize_bpmn_for_prosimos(xml)
    assert ElementTree.fromstring(normalized).find(f".//{{{NS}}}endEvent") is not None
    with pytest.raises(ValueError, match="Nessun evento di fine"):
        validate_simulation_bpmn(normalized)


def test_message_flows_do_not_replace_sequence_paths_between_pools():
    # Synthetic reproduction: ends exist but the only route crosses message flows.
    xml = model(
        NODES + '<sequenceFlow id="F1" sourceRef="S" targetRef="T"/>',
        '<process id="P2"><task id="Other"/></process>'
        '<collaboration id="C"><messageFlow id="M1" sourceRef="T" targetRef="Other"/>'
        '<messageFlow id="M2" sourceRef="Other" targetRef="E"/></collaboration>',
    )
    with pytest.raises(ValueError, match="flussi di messaggio tra pool"):
        validate_simulation_bpmn(normalize_bpmn_for_prosimos(xml))


def test_each_pool_requires_its_own_start_and_end():
    xml = model(extra='<process id="P2"><task id="Other"/></process>')
    with pytest.raises(ValueError, match="processo P2.*evento di inizio"):
        validate_simulation_bpmn(normalize_bpmn_for_prosimos(xml))


def test_valid_loop_with_exit_and_multiple_ends_pass():
    xml = model(
        NODES + FLOWS + '<endEvent id="E2"/>'
        '<sequenceFlow id="F3" sourceRef="T" targetRef="T"/>'
        '<sequenceFlow id="F4" sourceRef="T" targetRef="E2"/>'
    )
    normalized = normalize_bpmn_for_prosimos(xml)
    validate_simulation_bpmn(normalized)
    assert normalize_bpmn_for_prosimos(normalized) == normalized


def test_preflight_runs_before_storage_even_with_client_idempotency_key(monkeypatch):
    storage = Mock(side_effect=AssertionError("Invalid model reached storage"))
    monkeypatch.setattr("backend.simulation.service.find_active_run_by_key", storage)
    monkeypatch.setattr("backend.simulation.service.create_simulation_run", storage)
    bpmn = BpmnModelResponse(
        id="model", process_id="process", name="Synthetic", xml=model()
    )
    with pytest.raises(ValueError, match="Nessun evento di fine"):
        prepare_simulation_run(
            bpmn_model=bpmn,
            request=CreateSimulationRunRequest(
                current_bpmn_xml=model(NODES),
                idempotency_key="existing-key",
            ),
        )
    storage.assert_not_called()


def test_adapter_never_contacts_prosimos_with_invalid_bpmn(monkeypatch):
    client = Mock(side_effect=AssertionError("Invalid model reached HTTP"))
    monkeypatch.setattr("backend.simulation.prosimos_adapter.httpx.AsyncClient", client)
    request = ProsimosSimulationRequest(
        bpmn_xml=model(NODES),
        scenario=ProsimosScenario(payload={}, task_count=1, gateway_count=0),
        total_cases=1,
    )
    with pytest.raises(ProsimosError, match="Nessun evento di fine"):
        asyncio.run(run_prosimos_simulation(request))
    client.assert_not_called()


def test_a_process_started_by_an_event_based_gateway_gets_a_start_event_for_the_engine():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" id="D">
  <bpmn:process id="P">
    <bpmn:eventBasedGateway id="G" instantiate="true" eventGatewayType="Parallel"><bpmn:outgoing>F1</bpmn:outgoing><bpmn:outgoing>F2</bpmn:outgoing></bpmn:eventBasedGateway>
    <bpmn:intermediateCatchEvent id="Mail"><bpmn:messageEventDefinition /></bpmn:intermediateCatchEvent>
    <bpmn:intermediateCatchEvent id="Call"><bpmn:messageEventDefinition /></bpmn:intermediateCatchEvent>
    <bpmn:task id="A" />
    <bpmn:task id="B" />
    <bpmn:endEvent id="E" />
    <bpmn:sequenceFlow id="F1" sourceRef="G" targetRef="Mail" />
    <bpmn:sequenceFlow id="F2" sourceRef="G" targetRef="Call" />
    <bpmn:sequenceFlow id="F3" sourceRef="Mail" targetRef="A" />
    <bpmn:sequenceFlow id="F4" sourceRef="Call" targetRef="B" />
    <bpmn:sequenceFlow id="F5" sourceRef="A" targetRef="E" />
    <bpmn:sequenceFlow id="F6" sourceRef="B" targetRef="E" />
  </bpmn:process>
</bpmn:definitions>"""

    normalized = normalize_bpmn_for_prosimos(xml)
    root = ElementTree.fromstring(normalized)
    ns = {"bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL"}
    gateway = root.find(".//bpmn:eventBasedGateway", ns)
    (start,) = root.findall(".//bpmn:startEvent", ns)

    assert "instantiate" not in gateway.attrib and "eventGatewayType" not in gateway.attrib
    assert any(
        flow.get("sourceRef") == start.get("id") and flow.get("targetRef") == "G"
        for flow in root.findall(".//bpmn:sequenceFlow", ns)
    )
    validate_simulation_bpmn(normalized)


def test_a_link_pair_stays_one_path_for_the_engine():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" id="D">
  <bpmn:process id="P">
    <bpmn:startEvent id="S" />
    <bpmn:task id="A" />
    <bpmn:intermediateThrowEvent id="T"><bpmn:linkEventDefinition name="Al rimborso" /></bpmn:intermediateThrowEvent>
    <bpmn:intermediateCatchEvent id="C"><bpmn:linkEventDefinition name="Al rimborso" /></bpmn:intermediateCatchEvent>
    <bpmn:task id="B" />
    <bpmn:endEvent id="E" />
    <bpmn:sequenceFlow id="F1" sourceRef="S" targetRef="A" />
    <bpmn:sequenceFlow id="F2" sourceRef="A" targetRef="T" />
    <bpmn:sequenceFlow id="F3" sourceRef="C" targetRef="B" />
    <bpmn:sequenceFlow id="F4" sourceRef="B" targetRef="E" />
  </bpmn:process>
</bpmn:definitions>"""

    normalized = normalize_bpmn_for_prosimos(xml)
    flows = {
        (flow.get("sourceRef"), flow.get("targetRef"))
        for flow in ElementTree.fromstring(normalized).iter("{http://www.omg.org/spec/BPMN/20100524/MODEL}sequenceFlow")
    }

    assert ("A", "B") in flows
    validate_simulation_bpmn(normalized)


def test_event_sub_processes_and_compensation_activities_stay_out_of_the_engine():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" id="D">
  <bpmn:process id="P">
    <bpmn:startEvent id="S" />
    <bpmn:task id="A" />
    <bpmn:endEvent id="E" />
    <bpmn:subProcess id="Reclamo" triggeredByEvent="true"><bpmn:startEvent id="RS"><bpmn:messageEventDefinition /></bpmn:startEvent></bpmn:subProcess>
    <bpmn:task id="Storno" isForCompensation="true" />
    <bpmn:sequenceFlow id="F1" sourceRef="S" targetRef="A" />
    <bpmn:sequenceFlow id="F2" sourceRef="A" targetRef="E" />
  </bpmn:process>
</bpmn:definitions>"""

    normalized = normalize_bpmn_for_prosimos(xml)

    assert 'id="Reclamo"' not in normalized and 'id="Storno"' not in normalized
    validate_simulation_bpmn(normalized)
