"""Every BPMN 2.0 event definition the plan can name, on the events that may carry it.

OMG BPMN 2.0, 10.4: start, intermediate (catch/throw) and end events with
message, timer, conditional, signal, error, escalation, compensation, cancel,
link, terminate and multiple definitions.
"""

import pytest

from backend.bpmn import build_bpmn_semantic_model, semantic_model_to_bpmn_xml
from backend.bpmn.models import BPMNFlowNode
from backend.bpmn.soundness import analyze_control_flow
from backend.bpmn.validation import validate_bpmn_semantic_model
from backend.process_understanding import (
    ProcessActor,
    ProcessBoundaries,
    ProcessEvent,
    ProcessStep,
    ProcessUnderstanding,
)


def _process(*, path: list[str], events: list[ProcessEvent], steps: tuple[str, ...] = ("a", "b")) -> ProcessUnderstanding:
    return ProcessUnderstanding(
        title="Reclamo cliente",
        actors=[ProcessActor(id="ufficio", label="Ufficio reclami", kind="team")],
        boundaries=ProcessBoundaries(),
        steps=[ProcessStep(id=step, label=f"Passo {step}", actor_ids=["ufficio"]) for step in steps],
        events=events,
        main_success_path=path,
    )


def _compile(process: ProcessUnderstanding):
    return build_bpmn_semantic_model(process_id="Reclamo", process_name=process.title, process=process)


def _node(model, name: str):
    return next(node for node in model.flowNodes if node.name == name)


def _sound(model) -> None:
    structural = [issue for issue in validate_bpmn_semantic_model(model) if not issue.startswith("Soundness:")]
    assert structural == []
    assert not analyze_control_flow(model).errors


def test_a_start_event_takes_the_trigger_the_plan_names_even_a_multiple_one():
    conditional = _compile(_process(path=["a"], events=[
        ProcessEvent(id="s", label="Scorta sotto soglia", type="start", definition="conditional", condition="scorta < 10"),
    ]))
    multiple = _compile(_process(path=["a"], events=[
        ProcessEvent(id="s", label="Ordine e conferma", type="start", definition="multiple",
                     triggers=["message", "signal"], parallel_multiple=True),
    ]))

    start = _node(conditional, "Scorta sotto soglia")
    assert (start.eventDefinition, start.eventConditionExpression) == ("conditional", "scorta < 10")
    start = _node(multiple, "Ordine e conferma")
    assert (start.eventDefinition, start.triggers, start.parallelMultiple) == ("multiple", ["message", "signal"], True)
    xml = semantic_model_to_bpmn_xml(multiple, include_di=False)
    assert 'parallelMultiple="true"' in xml
    assert "<bpmn:messageEventDefinition" in xml and "<bpmn:signalEventDefinition" in xml


@pytest.mark.parametrize(
    ("definition", "tag"),
    [
        ("message", "messageEventDefinition"),
        ("error", "errorEventDefinition"),
        ("escalation", "escalationEventDefinition"),
        ("signal", "signalEventDefinition"),
        ("compensation", "compensateEventDefinition"),
    ],
)
def test_an_end_event_carries_the_result_the_plan_names(definition, tag):
    model = _compile(_process(path=["a"], events=[ProcessEvent(id="e", label="Pratica chiusa", type="end", definition=definition)]))

    end = _node(model, "Pratica chiusa")
    assert end.eventDefinition == definition
    assert f"<bpmn:{tag}" in semantic_model_to_bpmn_xml(model, include_di=False)


@pytest.mark.parametrize(
    ("definition", "direction", "node_type"),
    [
        ("signal", "throw", "intermediateThrowEvent"),
        ("signal", "catch", "intermediateCatchEvent"),
        ("conditional", "catch", "intermediateCatchEvent"),
        ("escalation", "catch", "intermediateThrowEvent"),  # only ever thrown
        ("compensation", "catch", "intermediateThrowEvent"),
        ("timer", "throw", "intermediateCatchEvent"),  # only ever waited for
    ],
)
def test_an_intermediate_event_sits_on_the_side_its_definition_allows(definition, direction, node_type):
    event = ProcessEvent(
        id="mid", label="Evento intermedio", type="intermediate", direction=direction,
        definition=definition, condition="pagamento registrato",
    )

    model = _compile(_process(path=["a", "mid", "b"], events=[event]))

    node = _node(model, "Evento intermedio")
    assert (node.type, node.eventDefinition) == (node_type, definition)
    _sound(model)


def test_a_none_intermediate_throw_marks_a_milestone():
    event = ProcessEvent(id="mid", label="Reclamo registrato", type="intermediate", direction="throw", definition="none")

    model = _compile(_process(path=["a", "mid", "b"], events=[event]))

    node = _node(model, "Reclamo registrato")
    assert (node.type, node.eventDefinition) == ("intermediateThrowEvent", None)


def test_a_link_pair_replaces_the_flow_between_two_stretches_of_the_process():
    events = [
        ProcessEvent(id="vai", label="Al rimborso", type="intermediate", direction="throw", definition="link"),
        ProcessEvent(id="da", label="Al rimborso", type="intermediate", direction="catch", definition="link"),
    ]

    model = _compile(_process(path=["a", "vai", "da", "b"], events=events))

    throw = next(node for node in model.flowNodes if node.type == "intermediateThrowEvent")
    catch = next(node for node in model.flowNodes if node.type == "intermediateCatchEvent")
    assert not [flow for flow in model.sequenceFlows if flow.sourceRef == throw.id or flow.targetRef == catch.id]
    assert '<bpmn:linkEventDefinition name="Al rimborso" />' in semantic_model_to_bpmn_xml(model, include_di=False)
    _sound(model)
    assert "<bpmndi:BPMNDiagram" in semantic_model_to_bpmn_xml(model)


def test_a_link_nothing_catches_is_a_broken_flow():
    events = [
        ProcessEvent(id="vai", label="Al rimborso", type="intermediate", direction="throw", definition="link"),
        ProcessEvent(id="da", label="Alla chiusura", type="intermediate", direction="catch", definition="link"),
    ]

    model = _compile(_process(path=["a", "vai", "da", "b"], events=events))

    assert {issue.code for issue in analyze_control_flow(model).errors} >= {"unpaired_link"}


def test_a_definition_the_event_cannot_carry_is_left_out_not_drawn_wrong():
    model = _compile(_process(path=["a"], events=[
        ProcessEvent(id="s", label="Errore iniziale", type="start", definition="error"),
        ProcessEvent(id="e", label="Fine", type="end", definition="multiple", triggers=["message"]),
    ]))

    assert _node(model, "Fine").eventDefinition is None


@pytest.mark.parametrize(
    "fields",
    [
        {"type": "startEvent", "eventDefinition": "link"},
        {"type": "intermediateCatchEvent", "eventDefinition": "escalation"},
        {"type": "intermediateThrowEvent", "eventDefinition": "timer"},
        {"type": "endEvent", "eventDefinition": "timer"},
        {"type": "startEvent", "eventDefinition": "multiple", "triggers": ["message"]},
        {"type": "endEvent", "eventDefinition": "multiple", "triggers": ["message", "signal"], "parallelMultiple": True},
    ],
)
def test_the_model_refuses_what_omg_does_not_allow(fields):
    with pytest.raises(ValueError):
        BPMNFlowNode(id="n", name="n", **fields)
