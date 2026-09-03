"""Serialize a `BPMNSemanticModel` to BPMN 2.0 XML, diagram interchange included.

Owns the deterministic layout of the compiled model (lane bands, flow-node
columns, pool shapes, edge waypoints). `layout_bpmn_di` in
`workspace_services.bpmn_canvas_edit` regenerates DI for hand-edited canvases;
this module owns DI for freshly compiled models.
"""

from __future__ import annotations

import json
from html import escape

from backend.bpmn._helpers import documentation_xml, element_documentation
from backend.bpmn.models import BPMNFlowNode, BPMNMessageFlow, BPMNSemanticModel

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
}


def _event_declarations(model: BPMNSemanticModel) -> tuple[list[str], dict[str, str]]:
    """Collect definitions-level <bpmn:message/signal/error> elements referenced
    by the model's events, plus a node-id -> declaration-id map for their refs.
    Message/signal/error events sharing a name share one declaration.
    """
    declarations: dict[tuple[str, str], str] = {}
    lines: list[str] = []
    ref_by_node: dict[str, str] = {}
    taken = {node.id for node in model.flowNodes} | {flow.id for flow in model.sequenceFlows}
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


def _event_definition_xml(kind: str, ref_id: str | None) -> str:
    spec = _REFERENCEABLE_EVENT_DEFINITIONS.get(kind)
    if spec and ref_id:
        return f'      <bpmn:{kind}EventDefinition {spec[1]}="{escape(ref_id)}" />'
    return f"      <bpmn:{kind}EventDefinition />"


def semantic_model_to_bpmn_xml(model: BPMNSemanticModel) -> str:
    incoming, outgoing = _flow_refs(model)
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
        if node.eventDefinition and node.type in _EVENT_DEFINITION_HOSTS:
            xml_parts.append(_event_definition_xml(node.eventDefinition, event_ref_by_node.get(node.id)))
        xml_parts.append(f"    </bpmn:{node.type}>")

    for flow in model.sequenceFlows:
        name = f' name="{escape(flow.name)}"' if flow.name else ""
        body: list[str] = []
        if flow.documentation or flow.sourceRefs:
            body.extend(
                documentation_xml(element_documentation(flow.documentation, flow.sourceRefs), indent="      ")
            )
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

    plane_element = (
        (model.collaborationId or f"Collaboration_{model.id}") if model.participants else model.id
    )
    xml_parts.extend(
        [
            "  </bpmn:process>",
            f'  <bpmndi:BPMNDiagram id="BPMNDiagram_{escape(model.id)}">',
            f'    <bpmndi:BPMNPlane id="BPMNPlane_{escape(model.id)}" bpmnElement="{escape(plane_element)}">',
        ]
    )
    positions, lane_shapes = _layout_model(model)
    pool_shapes, pool_positions = _collaboration_pool_shapes(model, positions, lane_shapes)
    for pool_shape in pool_shapes:
        pool_id = escape(str(pool_shape["id"]))
        xml_parts.extend(
            [
                f'      <bpmndi:BPMNShape id="{pool_id}_di" bpmnElement="{pool_id}" isHorizontal="true">',
                f'        <dc:Bounds x="{pool_shape["x"]}" y="{pool_shape["y"]}" width="{pool_shape["width"]}" height="{pool_shape["height"]}" />',
                "      </bpmndi:BPMNShape>",
            ]
        )
    for lane_shape in lane_shapes:
        lane_shape_id = escape(str(lane_shape["id"]))
        xml_parts.extend(
            [
                f'      <bpmndi:BPMNShape id="{lane_shape_id}_di" bpmnElement="{lane_shape_id}" isHorizontal="true">',
                f'        <dc:Bounds x="{lane_shape["x"]}" y="{lane_shape["y"]}" width="{lane_shape["width"]}" height="{lane_shape["height"]}" />',
                "      </bpmndi:BPMNShape>",
            ]
        )
    for node in model.flowNodes:
        pos = positions[node.id]
        node_di_id = escape(node.id)
        xml_parts.extend(
            [
                f'      <bpmndi:BPMNShape id="{node_di_id}_di" bpmnElement="{node_di_id}">',
                f'        <dc:Bounds x="{pos["x"]}" y="{pos["y"]}" width="{pos["width"]}" height="{pos["height"]}" />',
                "      </bpmndi:BPMNShape>",
            ]
        )

    artifacts = [*model.dataObjects, *model.dataStores]
    data_positions = _layout_data_objects(artifacts, positions)
    for artifact in artifacts:
        pos = data_positions[artifact.id]
        artifact_di_id = escape(artifact.id)
        xml_parts.extend(
            [
                f'      <bpmndi:BPMNShape id="{artifact_di_id}_di" bpmnElement="{artifact_di_id}">',
                f'        <dc:Bounds x="{pos["x"]}" y="{pos["y"]}" width="{pos["width"]}" height="{pos["height"]}" />',
                "      </bpmndi:BPMNShape>",
            ]
        )

    annotation_positions = _layout_text_annotations(model.textAnnotations)
    for annotation in model.textAnnotations:
        pos = annotation_positions[annotation.id]
        annotation_di_id = escape(annotation.id)
        xml_parts.extend(
            [
                f'      <bpmndi:BPMNShape id="{annotation_di_id}_di" bpmnElement="{annotation_di_id}">',
                f'        <dc:Bounds x="{pos["x"]}" y="{pos["y"]}" width="{pos["width"]}" height="{pos["height"]}" />',
                "      </bpmndi:BPMNShape>",
            ]
        )

    for flow in model.sequenceFlows:
        for line in _edge_xml(flow.id, flow.sourceRef, flow.targetRef, positions, flow.name):
            xml_parts.append(line)
    connectable_positions = {**positions, **data_positions, **annotation_positions}
    for association in model.associations:
        source = connectable_positions.get(association.sourceRef)
        target = connectable_positions.get(association.targetRef)
        if source and target:
            xml_parts.extend(_association_edge_xml(association.id, source, target))

    message_flow_positions = {**positions, **pool_positions}
    for message_flow in model.messageFlows:
        source_pos = message_flow_positions.get(message_flow.sourceRef)
        target_pos = message_flow_positions.get(message_flow.targetRef)
        if source_pos and target_pos:
            for line in _message_flow_edge_xml(message_flow, source_pos, target_pos):
                xml_parts.append(line)

    xml_parts.extend(["    </bpmndi:BPMNPlane>", "  </bpmndi:BPMNDiagram>", "</bpmn:definitions>"])
    return "\n".join(xml_parts)


def _collaboration_semantic_xml(model: BPMNSemanticModel) -> list[str]:
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
        name = f' name="{escape(message_flow.name)}"' if message_flow.name else ""
        header = (
            f'    <bpmn:messageFlow id="{escape(message_flow.id)}" '
            f'sourceRef="{escape(message_flow.sourceRef)}" '
            f'targetRef="{escape(message_flow.targetRef)}"{name}'
        )
        if message_flow.documentation or message_flow.sourceRefs:
            lines.append(header + ">")
            lines.extend(
                documentation_xml(
                    element_documentation(message_flow.documentation, message_flow.sourceRefs),
                    indent="      ",
                )
            )
            lines.append("    </bpmn:messageFlow>")
        else:
            lines.append(header + " />")
    lines.append("  </bpmn:collaboration>")
    return lines


def _process_documentation(model: BPMNSemanticModel) -> str:
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
    open_tag = f'    <bpmn:{tag} id="{escape(artifact_id)}" name="{escape(name)}"'
    if documentation or source_refs:
        return [
            open_tag + ">",
            *documentation_xml(element_documentation(documentation, source_refs), indent="      "),
            f"    </bpmn:{tag}>",
        ]
    return [open_tag + " />"]


def _flow_refs(model: BPMNSemanticModel) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    incoming: dict[str, list[str]] = {node.id: [] for node in model.flowNodes}
    outgoing: dict[str, list[str]] = {node.id: [] for node in model.flowNodes}
    for flow in model.sequenceFlows:
        outgoing.setdefault(flow.sourceRef, []).append(flow.id)
        incoming.setdefault(flow.targetRef, []).append(flow.id)
    return incoming, outgoing


def _node_size(node: BPMNFlowNode) -> tuple[int, int]:
    if node.type in {"startEvent", "endEvent", "intermediateCatchEvent", "intermediateThrowEvent"}:
        return 44, 44
    if node.type == "boundaryEvent":
        return 36, 36
    if node.type in {"exclusiveGateway", "parallelGateway", "inclusiveGateway", "eventBasedGateway"}:
        return 68, 68
    return 188, 92


def _layout_model(
    model: BPMNSemanticModel,
) -> tuple[dict[str, dict[str, float]], list[dict[str, float | str]]]:
    lane_index_by_id = {lane.id: index for index, lane in enumerate(model.lanes)}
    lane_height = 180
    top = 150
    left = 110
    lane_label_width = 70
    x_gap = 230
    positions: dict[str, dict[str, float]] = {}

    ranked_nodes = [node for node in model.flowNodes if node.type != "boundaryEvent"]
    for rank, node in enumerate(ranked_nodes):
        width, height = _node_size(node)
        lane_index = lane_index_by_id.get(node.laneId or "", 0)
        y = top + lane_index * lane_height + (lane_height - height) / 2
        positions[node.id] = {
            "x": left + lane_label_width + 70 + rank * x_gap,
            "y": y,
            "width": width,
            "height": height,
        }

    for node in model.flowNodes:
        if node.type != "boundaryEvent":
            continue
        width, height = _node_size(node)
        attached = positions.get(node.attachedToRef or "")
        if attached is not None:
            positions[node.id] = {
                "x": attached["x"] + attached["width"] * 0.62,
                "y": attached["y"] + attached["height"] - height / 2,
                "width": width,
                "height": height,
            }
        else:
            positions[node.id] = {"x": left, "y": top, "width": width, "height": height}

    right = max((pos["x"] + pos["width"] for pos in positions.values()), default=900) + 90
    lane_shapes = [
        {
            "id": lane.id,
            "x": left,
            "y": top + index * lane_height,
            "width": max(900, right - left),
            "height": lane_height,
        }
        for index, lane in enumerate(model.lanes)
    ]
    return positions, lane_shapes


def _collaboration_pool_shapes(
    model: BPMNSemanticModel,
    node_positions: dict[str, dict[str, float]],
    lane_shapes: list[dict[str, float | str]],
) -> tuple[list[dict[str, float | str]], dict[str, dict[str, float]]]:
    if not model.participants:
        return [], {}

    primary = next((p for p in model.participants if p.processRef), None)
    externals = [p for p in model.participants if not p.processRef]

    boxes: list[tuple[float, float, float, float]] = [
        (float(shape["x"]), float(shape["y"]), float(shape["width"]), float(shape["height"]))
        for shape in lane_shapes
    ]
    boxes.extend((pos["x"], pos["y"], pos["width"], pos["height"]) for pos in node_positions.values())
    if boxes:
        min_x = min(box[0] for box in boxes)
        min_y = min(box[1] for box in boxes)
        max_x = max(box[0] + box[2] for box in boxes)
        max_y = max(box[1] + box[3] for box in boxes)
    else:
        min_x, min_y, max_x, max_y = 110.0, 150.0, 1000.0, 330.0

    pool_left = min_x - 30
    pool_width = (max_x - pool_left) + 40
    primary_top = min_y - 30
    primary_height = max(max_y - primary_top + 30, 160.0)

    shapes: list[dict[str, float | str]] = []
    pool_positions: dict[str, dict[str, float]] = {}
    if primary is not None:
        box = {"x": pool_left, "y": primary_top, "width": pool_width, "height": primary_height}
        pool_positions[primary.id] = box
        shapes.append({"id": primary.id, **box})

    external_top = primary_top + primary_height + 40
    for participant in externals:
        box = {"x": pool_left, "y": external_top, "width": pool_width, "height": 120.0}
        pool_positions[participant.id] = box
        shapes.append({"id": participant.id, **box})
        external_top += 160

    return shapes, pool_positions


def _layout_text_annotations(annotations: list) -> dict[str, dict[str, float]]:
    return {
        annotation.id: {"x": 180 + ((index - 1) * 230), "y": 40, "width": 190, "height": 70}
        for index, annotation in enumerate(annotations, start=1)
    }


def _layout_data_objects(
    data_objects: list,
    positions: dict[str, dict[str, float]],
) -> dict[str, dict[str, float]]:
    layout: dict[str, dict[str, float]] = {}
    per_source_count: dict[str, int] = {}

    for index, data_object in enumerate(data_objects, start=1):
        source_id = data_object.sourceNodeRef or ""
        source = positions.get(source_id)
        if source:
            offset = per_source_count.get(source_id, 0)
            per_source_count[source_id] = offset + 1
            x = source["x"] + 20 + offset * 48
            y = source["y"] + source["height"] + 34
        else:
            x = 180 + (index - 1) * 130
            y = 420
        layout[data_object.id] = {"x": x, "y": y, "width": 64, "height": 54}

    return layout


def _edge_xml(
    flow_id: str,
    source_ref: str,
    target_ref: str,
    positions: dict[str, dict[str, float]],
    name: str | None,
) -> list[str]:
    source = positions.get(source_ref)
    target = positions.get(target_ref)
    if source is None or target is None:
        # dangling sequence flow (model rebuilt from an inconsistent dict) — skip
        return []
    start_x = source["x"] + source["width"]
    start_y = source["y"] + source["height"] / 2
    end_x = target["x"]
    end_y = target["y"] + target["height"] / 2
    lines = [
        f'      <bpmndi:BPMNEdge id="{escape(flow_id)}_di" bpmnElement="{escape(flow_id)}">',
        f'        <di:waypoint x="{start_x}" y="{start_y}" />',
    ]
    if abs(start_y - end_y) > 1:
        mid_x = start_x + max(60, (end_x - start_x) / 2)
        lines.extend(
            [
                f'        <di:waypoint x="{mid_x}" y="{start_y}" />',
                f'        <di:waypoint x="{mid_x}" y="{end_y}" />',
            ]
        )
    lines.append(f'        <di:waypoint x="{end_x}" y="{end_y}" />')
    if name:
        label_width = min(150, max(70, len(name) * 6))
        lines.extend(
            [
                "        <bpmndi:BPMNLabel>",
                f'          <dc:Bounds x="{(start_x + end_x) / 2 - label_width / 2}" y="{min(start_y, end_y) - 32}" width="{label_width}" height="24" />',
                "        </bpmndi:BPMNLabel>",
            ]
        )
    lines.append("      </bpmndi:BPMNEdge>")
    return lines


def _association_edge_xml(
    association_id: str,
    source: dict[str, float],
    target: dict[str, float],
) -> list[str]:
    escaped = escape(association_id)
    return [
        f'      <bpmndi:BPMNEdge id="{escaped}_di" bpmnElement="{escaped}">',
        f'        <di:waypoint x="{source["x"] + source["width"] / 2}" y="{source["y"] + source["height"] / 2}" />',
        f'        <di:waypoint x="{target["x"] + target["width"] / 2}" y="{target["y"] + target["height"] / 2}" />',
        "      </bpmndi:BPMNEdge>",
    ]


def _message_flow_edge_xml(
    message_flow: BPMNMessageFlow,
    source: dict[str, float],
    target: dict[str, float],
) -> list[str]:
    start_x = source["x"] + source["width"] / 2
    end_x = target["x"] + target["width"] / 2
    if source["y"] <= target["y"]:
        start_y = source["y"] + source["height"]
        end_y = target["y"]
    else:
        start_y = source["y"]
        end_y = target["y"] + target["height"]
    lines = [
        f'      <bpmndi:BPMNEdge id="{escape(message_flow.id)}_di" bpmnElement="{escape(message_flow.id)}">',
        f'        <di:waypoint x="{start_x}" y="{start_y}" />',
        f'        <di:waypoint x="{end_x}" y="{end_y}" />',
    ]
    if message_flow.name:
        label_width = min(180, max(80, len(message_flow.name) * 6))
        lines.extend(
            [
                "        <bpmndi:BPMNLabel>",
                f'          <dc:Bounds x="{(start_x + end_x) / 2 - label_width / 2}" '
                f'y="{(start_y + end_y) / 2 - 12}" width="{label_width}" height="24" />',
                "        </bpmndi:BPMNLabel>",
            ]
        )
    lines.append("      </bpmndi:BPMNEdge>")
    return lines
