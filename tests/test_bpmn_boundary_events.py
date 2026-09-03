"""Boundary events: escalation event definition + root declaration."""

import pytest
from pydantic import ValidationError

from backend.bpmn import build_bpmn_semantic_model, semantic_model_to_bpmn_xml
from backend.process_understanding import (
    ProcessActor,
    ProcessExceptionPath,
    ProcessStep,
    ProcessUnderstanding,
)


def _model(*exceptions: ProcessExceptionPath):
    """
    Build a BPMN semantic model for a two-step process with the specified exception path.
    
    Parameters:
        *exceptions: Exception paths to include in the process model.
    
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
        exceptions=list(exceptions),
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


@pytest.mark.parametrize(
    ("kind", "expected_cancel_activity"),
    [
        ("timer", False),
        ("message", False),
        ("conditional", False),
        ("escalation", False),
        ("signal", False),
        ("error", True),
    ],
)
def test_explicit_exception_kind_overrides_misleading_trigger_text(
    kind: str, expected_cancel_activity: bool
):
    model = _model(
        ProcessExceptionPath(
            id=f"Exc_{kind}",
            label="Errore dopo cinque giorni",
            trigger="messaggio di errore dopo 5 giorni",
            handling="Gestisci eccezione",
            kind=kind,
            attached_to_step_id="T1",
            interrupting=False,
        )
    )

    boundary = next(n for n in model.flowNodes if n.type == "boundaryEvent")
    assert boundary.eventDefinition == kind
    assert boundary.cancelActivity is expected_cancel_activity
    assert f"<bpmn:{kind}EventDefinition" in semantic_model_to_bpmn_xml(model)

    forced_warnings = [
        warning for warning in model.model_warnings if "forzata a interrupting" in warning
    ]
    assert bool(forced_warnings) is (kind == "error")


def test_equal_escalations_share_one_root_declaration():
    exceptions = [
        ProcessExceptionPath(
            id=f"Exc_{step_id}",
            label="Passa al responsabile",
            trigger="soglia superata",
            handling="Gestisci escalation",
            kind="escalation",
            attached_to_step_id=step_id,
        )
        for step_id in ("T1", "T2")
    ]
    xml = semantic_model_to_bpmn_xml(_model(*exceptions))

    escalation_id = _attr(xml, "<bpmn:escalation ", "id")
    assert xml.count("<bpmn:escalation id=") == 1
    assert xml.count(f'escalationRef="{escalation_id}"') == 2


def test_explicit_conditional_exception_without_a_trigger_is_skipped():
    model = _model(
        ProcessExceptionPath(
            id="Exc_Conditional",
            label="Condizione sconosciuta",
            trigger="   ",
            handling="Gestisci eccezione",
            kind="conditional",
            attached_to_step_id="T1",
        )
    )

    assert not any(node.type == "boundaryEvent" for node in model.flowNodes)
    assert any(
        "boundary event condizionale non generato" in warning
        for warning in model.model_warnings
    )
    assert "conditionalEventDefinition" not in semantic_model_to_bpmn_xml(model)


def test_unknown_exception_kind_is_rejected():
    with pytest.raises(ValidationError, match="kind"):
        ProcessExceptionPath(
            id="Exc",
            label="Eccezione",
            kind="cancellation",
        )


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
