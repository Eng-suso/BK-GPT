"""Serializer: definitions-level message/signal/error declarations and refs."""

import re
from xml.etree import ElementTree

import pytest

from backend.bpmn import semantic_model_to_bpmn_xml
from backend.bpmn.models import BPMNFlowNode, BPMNSemanticModel, BPMNSequenceFlow


def _model(nodes: list[BPMNFlowNode], flows: list[tuple[str, str]]) -> BPMNSemanticModel:
    return BPMNSemanticModel(
        id="P",
        name="P",
        flowNodes=nodes,
        sequenceFlows=[BPMNSequenceFlow(id=f"F{i}", sourceRef=s, targetRef=t) for i, (s, t) in enumerate(flows)],
    )


def test_message_events_sharing_a_name_share_one_declaration():
    model = _model(
        [
            BPMNFlowNode(id="s", type="startEvent", name="s"),
            BPMNFlowNode(id="g", type="eventBasedGateway", name="g"),
            BPMNFlowNode(id="c1", type="intermediateCatchEvent", name="Conferma cliente", eventDefinition="message"),
            BPMNFlowNode(id="c2", type="intermediateCatchEvent", name="Conferma cliente", eventDefinition="message"),
            BPMNFlowNode(id="e", type="endEvent", name="e"),
        ],
        [("s", "g"), ("g", "c1"), ("g", "c2"), ("c1", "e"), ("c2", "e")],
    )
    xml = semantic_model_to_bpmn_xml(model)

    assert xml.count("<bpmn:message ") == 1
    message_id = re.search(r'<bpmn:message id="([^"]+)" name="Conferma cliente" />', xml).group(1)
    assert xml.count(f'messageEventDefinition messageRef="{message_id}"') == 2
    # the declaration is a child of <bpmn:definitions>, before <bpmn:process>
    assert xml.index("<bpmn:message ") < xml.index("<bpmn:process ")


def test_distinct_event_names_get_distinct_declarations():
    model = _model(
        [
            BPMNFlowNode(id="s", type="startEvent", name="s"),
            BPMNFlowNode(id="g", type="eventBasedGateway", name="g"),
            BPMNFlowNode(id="c1", type="intermediateCatchEvent", name="Risposta email", eventDefinition="message"),
            BPMNFlowNode(id="c2", type="intermediateCatchEvent", name="Timeout SLA", eventDefinition="signal"),
            BPMNFlowNode(id="e", type="endEvent", name="e"),
        ],
        [("s", "g"), ("g", "c1"), ("g", "c2"), ("c1", "e"), ("c2", "e")],
    )
    xml = semantic_model_to_bpmn_xml(model)

    assert xml.count("<bpmn:message ") == 1
    assert xml.count("<bpmn:signal ") == 1
    assert '<bpmn:signalEventDefinition signalRef=' in xml


def test_error_boundary_event_declares_a_root_error():
    model = _model(
        [
            BPMNFlowNode(id="s", type="startEvent", name="s"),
            BPMNFlowNode(id="a", type="task", name="a"),
            BPMNFlowNode(id="b", type="boundaryEvent", name="Pagamento rifiutato", eventDefinition="error", attachedToRef="a"),
            BPMNFlowNode(id="h", type="task", name="Gestisci rifiuto"),
            BPMNFlowNode(id="e", type="endEvent", name="e"),
        ],
        [("s", "a"), ("a", "e"), ("b", "h"), ("h", "e")],
    )
    xml = semantic_model_to_bpmn_xml(model)

    error_id = re.search(r'<bpmn:error id="([^"]+)" name="Pagamento rifiutato" />', xml).group(1)
    assert f'<bpmn:errorEventDefinition errorRef="{error_id}" />' in xml


def test_timer_and_conditional_events_stay_inline_without_a_declaration():
    model = _model(
        [
            BPMNFlowNode(id="s", type="startEvent", name="s"),
            BPMNFlowNode(id="c", type="intermediateCatchEvent", name="Attendi 3 giorni", eventDefinition="timer"),
            BPMNFlowNode(id="e", type="endEvent", name="e"),
        ],
        [("s", "c"), ("c", "e")],
    )
    xml = semantic_model_to_bpmn_xml(model)

    assert "<bpmn:message " not in xml
    assert "<bpmn:signal " not in xml
    assert "<bpmn:timerEventDefinition />" in xml


def test_message_declaration_avoids_every_serialized_semantic_id():
    model = BPMNSemanticModel(
        id="Message_1",
        name="Collision",
        flowNodes=[
            BPMNFlowNode(
                id="catch",
                type="intermediateCatchEvent",
                name="Incoming message",
                eventDefinition="message",
            ),
        ],
        sequenceFlows=[],
    )

    xml = semantic_model_to_bpmn_xml(model)
    ids = [
        element.attrib["id"]
        for element in ElementTree.fromstring(xml).iter()
        if "id" in element.attrib
    ]

    assert '<bpmn:message id="Message_2"' in xml
    assert len(ids) == len(set(ids))


def test_conditionless_conditional_event_is_rejected():
    model = _model(
        [
            BPMNFlowNode(
                id="conditional",
                type="intermediateCatchEvent",
                name="Unspecified condition",
                eventDefinition="conditional",
            ),
        ],
        [],
    )

    with pytest.raises(ValueError, match="require an explicit condition"):
        semantic_model_to_bpmn_xml(model)
