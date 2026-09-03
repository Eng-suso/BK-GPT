"""Intermediate events: throwing vs catching."""

from backend.bpmn import build_bpmn_semantic_model, semantic_model_to_bpmn_xml
from backend.process_understanding import (
    ProcessEvent,
    ProcessFlowEdge,
    ProcessStep,
    ProcessUnderstanding,
)


def _compile(events: list[ProcessEvent]) -> object:
    """
    Build a BPMN semantic model for a two-step process containing the supplied events.
    
    Parameters:
    	events (list[ProcessEvent]): Events to include between the preparation and archival steps.
    
    Returns:
    	object: The compiled BPMN semantic model.
    """
    process = ProcessUnderstanding(
        title="Notifica",
        steps=[
            ProcessStep(id="T1", label="Prepara comunicazione"),
            ProcessStep(id="T2", label="Archivia esito"),
        ],
        sequence=["T1", "T2"],
        main_success_path=["T1", "T2"],
        events=events,
        flow_edges=[
            ProcessFlowEdge(id="E1", source_id="T1", target_id="Evt", label="pronto"),
            ProcessFlowEdge(id="E2", source_id="Evt", target_id="T2", label="fatto"),
        ],
        unknowns=[],
    )
    return build_bpmn_semantic_model(process_id="P", process_name="Notifica", process=process)


def test_throwing_event_compiles_to_an_intermediate_throw_event():
    model = _compile(
        [ProcessEvent(id="Evt", label="Invia notifica al cliente", type="message", direction="throw")]
    )
    node = next(n for n in model.flowNodes if n.name == "Invia notifica al cliente")
    assert node.type == "intermediateThrowEvent"
    assert "<bpmn:intermediateThrowEvent" in semantic_model_to_bpmn_xml(model)


def test_event_without_a_direction_still_catches():
    model = _compile([ProcessEvent(id="Evt", label="Attendi conferma", type="message")])
    node = next(n for n in model.flowNodes if n.name == "Attendi conferma")
    assert node.type == "intermediateCatchEvent"
