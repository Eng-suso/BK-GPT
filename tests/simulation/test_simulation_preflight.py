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
