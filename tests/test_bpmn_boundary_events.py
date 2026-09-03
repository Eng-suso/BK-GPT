"""Boundary events: escalation event definition + root declaration."""

from backend.bpmn import build_bpmn_semantic_model, semantic_model_to_bpmn_xml
from backend.process_understanding import (
    ProcessActor,
    ProcessExceptionPath,
    ProcessStep,
    ProcessUnderstanding,
)


def _model(exception: ProcessExceptionPath):
    """
    Build a BPMN semantic model for a two-step process with the specified exception path.
    
    Parameters:
        exception (ProcessExceptionPath): Exception path to include in the process model.
    
    Returns:
        The generated BPMN semantic model.
    """
    process = ProcessUnderstanding(
        title="Pratica",
        actors=[ProcessActor(id="A", label="Back office", kind="team")],
        steps=[
            ProcessStep(id="T1", label="Lavora pratica", actor_ids=["A"]),
            ProcessStep(id="T2", label="Chiudi pratica", actor_ids=["A"]),
        ],
        sequence=["T1", "T2"],
        main_success_path=["T1", "T2"],
        exceptions=[exception],
        unknowns=[],
    )
    return build_bpmn_semantic_model(process_id="P", process_name="P", process=process)


def test_escalation_exception_compiles_to_an_escalation_boundary_event():
    model = _model(
        ProcessExceptionPath(
            id="Exc",
            label="Caso passato al responsabile",
            trigger="il responsabile di sede prende in carico",
            handling="Il responsabile prende in carico",
            kind="escalation",
            attached_to_step_id="T1",
            interrupting=False,
        )
    )
    boundary = next(n for n in model.flowNodes if n.type == "boundaryEvent")
    assert boundary.eventDefinition == "escalation"
    assert boundary.cancelActivity is False  # escalation can be non-interrupting

    xml = semantic_model_to_bpmn_xml(model)
    escalation_id = _attr(xml, "<bpmn:escalation ", "id")
    assert f'<bpmn:escalationEventDefinition escalationRef="{escalation_id}" />' in xml


def _attr(xml: str, tag: str, name: str) -> str:
    """
    Extract the first occurrence of a named attribute from an XML tag.
    
    Parameters:
    	xml (str): XML text to search.
    	tag (str): Tag pattern to match.
    	name (str): Attribute name to extract.
    
    Returns:
    	str: Value of the first matching attribute.
    """
    import re

    return re.search(tag + r'[^>]*\b' + name + r'="([^"]+)"', xml).group(1)
