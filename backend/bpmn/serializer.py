"""Serialize semantics; CanvasLayoutPolicy owns all generated geometry."""

from __future__ import annotations

import json
from html import escape

from backend.bpmn._helpers import documentation_xml, element_documentation
from backend.bpmn.models import (
    ACTIVITY_NODE_TYPES as _ACTIVITY_NODE_TYPES,
    BPMNSemanticModel,
)

# Event nodes that may carry an <bpmn:xxxEventDefinition> child.
_EVENT_DEFINITION_HOSTS = frozenset(
    {"startEvent", "endEvent", "intermediateCatchEvent", "intermediateThrowEvent", "boundaryEvent"}
)
# Event definitions that resolve to a reusable definitions-level root element.
# (kind -> (root tag, ref attribute, id prefix))
_REFERENCEABLE_EVENT_DEFINITIONS = {
    "message": ("message", "messageRef", "Message"),
    "signal": ("signal", "signalRef", "Signal"),
    "error": ("error", "errorRef", "Error"),
    "escalation": ("escalation", "escalationRef", "Escalation"),
}


def _serialized_semantic_ids(model: BPMNSemanticModel) -> set[str]:
    """Return every ID emitted for a semantic BPMN element.

    Args:
        model: The BPMNSemanticModel to extract IDs from.

    Returns:
        A set of all semantic element IDs in the model.
    """
    ids = {
        f"Definitions_{model.id}",
        model.id,
        *(lane.id for lane in model.lanes),
        *(participant.id for participant in model.participants),
        *(message_flow.id for message_flow in model.messageFlows),
        *(node.id for node in model.flowNodes),
        *(flow.id for flow in model.sequenceFlows),
        *(artifact.id for artifact in (*model.dataObjects, *model.dataStores)),
        *(annotation.id for annotation in model.textAnnotations),
        *(association.id for association in model.associations),
    }
    if model.lanes:
        ids.add(f"{model.id}_LaneSet")
    if model.participants:
        ids.add(model.collaborationId or f"Collaboration_{model.id}")
    return ids


def _event_declarations(model: BPMNSemanticModel) -> tuple[list[str], dict[str, str]]:
    """Build reusable BPMN event declarations and node references.
    
    Events with the same normalized name and definition type share a declaration.
    Generated declaration IDs are unique within the serialized model.
    
    Args:
        model: Input semantic model whose event definitions are treated as untrusted
            serialization data.
    
    Returns:
        A tuple containing XML declaration lines and a mapping from event node IDs
        to their declaration IDs.
    """
    declarations: dict[tuple[str, str], str] = {}
    lines: list[str] = []
    ref_by_node: dict[str, str] = {}
    taken = _serialized_semantic_ids(model)
    for node in model.flowNodes:
        spec = _REFERENCEABLE_EVENT_DEFINITIONS.get(node.eventDefinition or "")
        if spec is None or node.type not in _EVENT_DEFINITION_HOSTS:
            continue
        tag, _attr, prefix = spec
        key = (tag, " ".join((node.name or "").split()).casefold() or node.id)
        decl_id = declarations.get(key)
        if decl_id is None:
            ordinal = sum(1 for k in declarations if k[0] == tag) + 1
            decl_id = f"{prefix}_{ordinal}"
            while decl_id in taken:
                ordinal += 1
                decl_id = f"{prefix}_{ordinal}"
            taken.add(decl_id)
            declarations[key] = decl_id
            lines.append(f'  <bpmn:{tag} id="{escape(decl_id)}" name="{escape(node.name or decl_id)}" />')
        ref_by_node[node.id] = decl_id
    return lines, ref_by_node


def _loop_characteristics_xml(kind: str, condition: str | None = None) -> list[str]:
    """Serialize loop characteristics as BPMN XML lines.
    
    Args:
        kind: Loop characteristic kind. ``"standardLoop"`` produces a standard
            loop; ``"multiInstanceSequential"`` produces sequential multi-instance
            characteristics; all other values produce parallel multi-instance
            characteristics.
        condition: Untrusted optional formal loop condition for a standard loop.
            Whitespace is removed and XML-sensitive characters are escaped.
    
    Returns:
        XML lines representing the requested loop characteristics. No lines
        contain unescaped condition content.
    """
    if kind == "standardLoop":
        if condition and condition.strip():
            return [
                "      <bpmn:standardLoopCharacteristics>",
                '        <bpmn:loopCondition xsi:type="bpmn:tFormalExpression">'
                f"{escape(condition.strip())}</bpmn:loopCondition>",
                "      </bpmn:standardLoopCharacteristics>",
            ]
        return ["      <bpmn:standardLoopCharacteristics />"]
    is_sequential = "true" if kind == "multiInstanceSequential" else "false"
    return [f'      <bpmn:multiInstanceLoopCharacteristics isSequential="{is_sequential}" />']


def _event_definition_xml(
    kind: str, ref_id: str | None, condition_expression: str | None
) -> str:
    """Generate an escaped BPMN event-definition XML fragment.
    
    Args:
        kind: Event definition type, such as ``timer``, ``message``, or
            ``conditional``. Treated as untrusted input.
        ref_id: Optional declaration ID for referenceable event definitions.
            Treated as untrusted input.
        condition_expression: Condition text for conditional events. Surrounding
            whitespace is removed, and the value is treated as untrusted input.
    
    Returns:
        An XML fragment for the specified event definition. Referenceable
        definitions include ``ref_id`` when provided; conditional definitions
        include their required formal condition.
    
    Raises:
        ValueError: If ``kind`` is ``"conditional"`` and the condition is empty
            or contains only whitespace.
    
    The function does not perform persistence or other external side effects.
    """
    if kind == "conditional":
        condition = (condition_expression or "").strip()
        if not condition:
            raise ValueError("Conditional BPMN events require an explicit condition expression")
        return (
            "      <bpmn:conditionalEventDefinition>\n"
            '        <bpmn:condition xsi:type="bpmn:tFormalExpression">'
            f"{escape(condition)}</bpmn:condition>\n"
            "      </bpmn:conditionalEventDefinition>"
        )
    spec = _REFERENCEABLE_EVENT_DEFINITIONS.get(kind)
    if spec and ref_id:
        return f'      <bpmn:{kind}EventDefinition {spec[1]}="{escape(ref_id)}" />'
    return f"      <bpmn:{kind}EventDefinition />"


def semantic_model_to_bpmn_xml(model: BPMNSemanticModel, *, include_di: bool = True) -> str:
    """
    Serialize a semantic BPMN model into a BPMN 2.0 XML document with deterministic diagram interchange layout.
    
    Args:
        model (BPMNSemanticModel): Untrusted semantic model to serialize. Its identifiers, names, and textual content are XML-escaped, and the resulting document preserves BPMN references and supported event and loop declarations.
    
    Returns:
        str: Complete BPMN 2.0 XML document, including semantic elements and diagram interchange data.
    
    Side Effects:
        None. The function does not persist or modify external state.
    """
    incoming, outgoing = _flow_refs(model)
    gateway_ids = {node.id for node in model.flowNodes if node.type.endswith("Gateway")}
    xml_parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
        'xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" '
        'xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" '
        'xmlns:di="http://www.omg.org/spec/DD/20100524/DI" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        f'id="Definitions_{escape(model.id)}" targetNamespace="https://workspace.local/bpmn">',
    ]
    root_event_decls, event_ref_by_node = _event_declarations(model)
    xml_parts.extend(root_event_decls)
    xml_parts.extend(_collaboration_semantic_xml(model))
    xml_parts.append(
        f'  <bpmn:process id="{escape(model.id)}" name="{escape(model.name)}" isExecutable="false">'
    )
    process_documentation = _process_documentation(model)
    if process_documentation:
        xml_parts.extend(documentation_xml(process_documentation, indent="    "))

    if model.lanes:
        xml_parts.append(f'    <bpmn:laneSet id="{escape(model.id)}_LaneSet">')
        for lane in model.lanes:
            xml_parts.append(f'      <bpmn:lane id="{escape(lane.id)}" name="{escape(lane.name)}">')
            for ref in lane.flowNodeRefs:
                xml_parts.append(f"        <bpmn:flowNodeRef>{escape(ref)}</bpmn:flowNodeRef>")
            xml_parts.append("      </bpmn:lane>")
        xml_parts.append("    </bpmn:laneSet>")

    for node in model.flowNodes:
        attrs = f' id="{escape(node.id)}" name="{escape(node.name)}"'
        if node.type == "boundaryEvent" and node.attachedToRef:
            attrs += f' attachedToRef="{escape(node.attachedToRef)}"'
            if not node.cancelActivity:
                attrs += ' cancelActivity="false"'
        if node.defaultFlowId and node.type in {"exclusiveGateway", "inclusiveGateway"}:
            attrs += f' default="{escape(node.defaultFlowId)}"'
        xml_parts.append(f"    <bpmn:{node.type}{attrs}>")
        if node.documentation or node.sourceRefs:
            xml_parts.extend(
                documentation_xml(element_documentation(node.documentation, node.sourceRefs), indent="      ")
            )
        if node.type != "boundaryEvent":
            for flow_id in incoming[node.id]:
                xml_parts.append(f"      <bpmn:incoming>{escape(flow_id)}</bpmn:incoming>")
        for flow_id in outgoing[node.id]:
            xml_parts.append(f"      <bpmn:outgoing>{escape(flow_id)}</bpmn:outgoing>")
        if node.loopCharacteristics != "none" and node.type in _ACTIVITY_NODE_TYPES:
            xml_parts.extend(
                _loop_characteristics_xml(node.loopCharacteristics, node.loopConditionExpression)
            )
        if node.eventDefinition and node.type in _EVENT_DEFINITION_HOSTS:
            xml_parts.append(
                _event_definition_xml(
                    node.eventDefinition,
                    event_ref_by_node.get(node.id),
                    node.eventConditionExpression,
                )
            )
        xml_parts.append(f"    </bpmn:{node.type}>")

    for flow in model.sequenceFlows:
        visible_name = flow.name if flow.sourceRef in gateway_ids else None
        name = f' name="{escape(visible_name)}"' if visible_name else ""
        body: list[str] = []
        if flow.documentation or flow.sourceRefs:
            body.extend(
                documentation_xml(element_documentation(flow.documentation, flow.sourceRefs), indent="      ")
            )
        if flow.name and not visible_name:
            body.extend(documentation_xml(flow.name, indent="      "))
        if flow.conditionExpression:
            body.append(
                '      <bpmn:conditionExpression xsi:type="bpmn:tFormalExpression">'
                f"{escape(flow.conditionExpression)}</bpmn:conditionExpression>"
            )
        open_tag = (
            f'    <bpmn:sequenceFlow id="{escape(flow.id)}" '
            f'sourceRef="{escape(flow.sourceRef)}" targetRef="{escape(flow.targetRef)}"{name}'
        )
        if body:
            xml_parts.append(open_tag + ">")
            xml_parts.extend(body)
            xml_parts.append("    </bpmn:sequenceFlow>")
        else:
            xml_parts.append(open_tag + " />")

    for data_object in model.dataObjects:
        xml_parts.extend(_artifact_xml("dataObjectReference", data_object.id, data_object.name,
                                       data_object.documentation, data_object.sourceRefs))
    for data_store in model.dataStores:
        xml_parts.extend(_artifact_xml("dataStoreReference", data_store.id, data_store.name,
                                       data_store.documentation, data_store.sourceRefs))
    for annotation in model.textAnnotations:
        body = documentation_xml(
            element_documentation("", annotation.sourceRefs), indent="      "
        ) if annotation.sourceRefs else []
        xml_parts.append(f'    <bpmn:textAnnotation id="{escape(annotation.id)}">')
        xml_parts.extend(body)  # <bpmn:documentation> must precede <bpmn:text> per XSD
        xml_parts.append(f"      <bpmn:text>{escape(annotation.text)}</bpmn:text>")
        xml_parts.append("    </bpmn:textAnnotation>")
    for association in model.associations:
        direction = (
            f' associationDirection="{_ASSOCIATION_DIRECTION[association.direction]}"'
            if association.direction != "none"
            else ""
        )
        xml_parts.append(
            f'    <bpmn:association id="{escape(association.id)}" '
            f'sourceRef="{escape(association.sourceRef)}" targetRef="{escape(association.targetRef)}"{direction} />'
        )

    xml_parts.extend(["  </bpmn:process>", "</bpmn:definitions>"])
    semantic_xml = "\n".join(xml_parts)
    if not include_di:
        return semantic_xml
    from backend.bpmn.canvas_layout import apply_enterprise_layout
    return apply_enterprise_layout(semantic_xml)


def _collaboration_semantic_xml(model: BPMNSemanticModel) -> list[str]:
    """Generate the <bpmn:collaboration> semantic XML for participants and message flows.

    Args:
        model: The BPMNSemanticModel with participants and message flows.

    Returns:
        A list of XML lines for the collaboration element, or empty list if no participants.
    """
    if not model.participants:
        return []

    collaboration_id = model.collaborationId or f"Collaboration_{model.id}"
    lines = [f'  <bpmn:collaboration id="{escape(collaboration_id)}">']
    for participant in model.participants:
        process_ref = (
            f' processRef="{escape(participant.processRef)}"' if participant.processRef else ""
        )
        lines.append(
            f'    <bpmn:participant id="{escape(participant.id)}" '
            f'name="{escape(participant.name)}"{process_ref} />'
        )
    for message_flow in model.messageFlows:
        header = (
            f'    <bpmn:messageFlow id="{escape(message_flow.id)}" '
            f'sourceRef="{escape(message_flow.sourceRef)}" '
            f'targetRef="{escape(message_flow.targetRef)}"'
        )
        if message_flow.documentation or message_flow.sourceRefs or message_flow.name:
            lines.append(header + ">")
            if message_flow.documentation or message_flow.sourceRefs:
                lines.extend(
                    documentation_xml(
                        element_documentation(message_flow.documentation, message_flow.sourceRefs),
                        indent="      ",
                    )
                )
            if message_flow.name:
                lines.extend(documentation_xml(message_flow.name, indent="      "))
            lines.append("    </bpmn:messageFlow>")
        else:
            lines.append(header + " />")
    lines.append("  </bpmn:collaboration>")
    return lines


def _process_documentation(model: BPMNSemanticModel) -> str:
    """Build the process-level documentation embedding the semantic payload.

    Args:
        model: The BPMNSemanticModel with source ProcessUnderstanding and compilation plan.

    Returns:
        A JSON-encoded documentation string with the full semantic payload.
    """
    payload = {
        "schema": "delir.semantic_payload.v1",
        "process_understanding": model.sourceProcessUnderstanding,
        "bpmn_compilation_plan": model.compilationPlan.model_dump(mode="json") if model.compilationPlan else None,
    }
    return "DeliR semantic payload:\n" + json.dumps(payload, ensure_ascii=False, sort_keys=True)


_ASSOCIATION_DIRECTION = {"none": "None", "one": "One", "both": "Both"}


def _artifact_xml(
    tag: str, artifact_id: str, name: str, documentation: str | None, source_refs: list[str]
) -> list[str]:
    """Generate XML lines for a data artifact (dataObjectReference or dataStoreReference).

    Args:
        tag: The BPMN tag name (e.g., "dataObjectReference", "dataStoreReference").
        artifact_id: The ID of the artifact.
        name: The name of the artifact.
        documentation: Optional documentation string.
        source_refs: List of source reference IDs for traceability.

    Returns:
        A list of XML lines for the artifact element.
    """
    open_tag = f'    <bpmn:{tag} id="{escape(artifact_id)}" name="{escape(name)}"'
    if documentation or source_refs:
        return [
            open_tag + ">",
            *documentation_xml(element_documentation(documentation, source_refs), indent="      "),
            f"    </bpmn:{tag}>",
        ]
    return [open_tag + " />"]


def _flow_refs(model: BPMNSemanticModel) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Build incoming and outgoing flow reference maps for each node.

    Args:
        model: The BPMNSemanticModel with flow nodes and sequence flows.

    Returns:
        A tuple of (incoming_flows_by_node_id, outgoing_flows_by_node_id) dictionaries.
    """
    incoming: dict[str, list[str]] = {node.id: [] for node in model.flowNodes}
    outgoing: dict[str, list[str]] = {node.id: [] for node in model.flowNodes}
    for flow in model.sequenceFlows:
        outgoing.setdefault(flow.sourceRef, []).append(flow.id)
        incoming.setdefault(flow.targetRef, []).append(flow.id)
    return incoming, outgoing
















