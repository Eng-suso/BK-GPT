from __future__ import annotations

from dataclasses import asdict, dataclass
import xml.etree.ElementTree as ET


BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
BPMNDI_NS = "http://www.omg.org/spec/BPMN/20100524/DI"
DC_NS = "http://www.omg.org/spec/DD/20100524/DC"
DI_NS = "http://www.omg.org/spec/DD/20100524/DI"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"

ET.register_namespace("bpmn", BPMN_NS)
ET.register_namespace("bpmndi", BPMNDI_NS)
ET.register_namespace("dc", DC_NS)
ET.register_namespace("di", DI_NS)
ET.register_namespace("xsi", XSI_NS)

EDITABLE_BPMN_TYPES = {
    "process",
    "lane",
    "startEvent",
    "endEvent",
    "intermediateCatchEvent",
    "intermediateThrowEvent",
    "boundaryEvent",
    "task",
    "userTask",
    "serviceTask",
    "sendTask",
    "receiveTask",
    "manualTask",
    "businessRuleTask",
    "scriptTask",
    "subProcess",
    "exclusiveGateway",
    "parallelGateway",
    "inclusiveGateway",
    "eventBasedGateway",
    "sequenceFlow",
    "dataObjectReference",
    "dataStoreReference",
    "textAnnotation",
}

ADDABLE_BPMN_TYPES = {
    "startEvent",
    "endEvent",
    "task",
    "userTask",
    "serviceTask",
    "manualTask",
    "exclusiveGateway",
    "parallelGateway",
    "inclusiveGateway",
    "lane",
    "dataObjectReference",
    "textAnnotation",
}

FLOW_NODE_TYPES = {
    "startEvent",
    "endEvent",
    "intermediateCatchEvent",
    "intermediateThrowEvent",
    "boundaryEvent",
    "task",
    "userTask",
    "serviceTask",
    "sendTask",
    "receiveTask",
    "manualTask",
    "businessRuleTask",
    "scriptTask",
    "subProcess",
    "exclusiveGateway",
    "parallelGateway",
    "inclusiveGateway",
    "eventBasedGateway",
}

DATA_ARTIFACT_TYPES = {"dataObjectReference", "dataStoreReference"}
ANNOTATION_TYPES = {"textAnnotation"}
CANVAS_METADATA_ARTIFACT_TYPES = DATA_ARTIFACT_TYPES | ANNOTATION_TYPES | {"association"}

LAYOUT_LEFT = 140
LAYOUT_TOP = 190
LAYOUT_LANE_LABEL_WIDTH = 88
LAYOUT_COLUMN_GAP = 320
LAYOUT_ROW_GAP = 190
LAYOUT_LANE_ROW_HEIGHT = 190
LAYOUT_MAX_NODES_PER_ROW = 5
LAYOUT_MIN_NODE_GAP = 48
LAYOUT_MAX_READABLE_WIDTH = 1900


@dataclass(frozen=True)
class BpmnLayoutConfig:
    max_nodes_per_row: int = LAYOUT_MAX_NODES_PER_ROW
    column_gap: int = LAYOUT_COLUMN_GAP
    row_gap: int = LAYOUT_ROW_GAP
    lane_row_height: int = LAYOUT_LANE_ROW_HEIGHT
    annotation_columns: int = 4


def list_bpmn_elements(xml: str) -> list[dict]:
    root = _parse_bpmn_xml(xml)
    elements = []

    for element in root.iter():
        element_id = element.attrib.get("id")
        element_type = _local_name(element.tag)

        if not element_id or _namespace(element.tag) != BPMN_NS:
            continue
        if element_type not in EDITABLE_BPMN_TYPES:
            continue

        elements.append(
            {
                "id": element_id,
                "type": element_type,
                "name": element.attrib.get("name", ""),
                "documentation": _documentation_text(element),
            }
        )

    return elements


def add_bpmn_element(
    xml: str,
    element_type: str,
    name: str,
    element_id: str | None = None,
    documentation: str | None = None,
) -> tuple[str, dict]:
    if element_type not in ADDABLE_BPMN_TYPES:
        raise ValueError(f"Tipo BPMN non supportato: {element_type}")

    root = _parse_bpmn_xml(xml)
    process = _find_process(root)
    clean_id = _unique_element_id(root, element_id or _default_element_id(element_type, name))

    if element_type == "lane":
        parent = _ensure_lane_set(process)
    else:
        parent = process

    element = ET.Element(_bpmn_tag(element_type), {"id": clean_id})
    clean_name = name.strip()
    if clean_name:
        element.set("name", clean_name)
    if documentation:
        _replace_documentation(element, documentation.strip())

    parent.append(element)
    updated_xml = layout_bpmn_di(_xml_to_string(root))
    return updated_xml, {
        "action": "add",
        "id": clean_id,
        "type": element_type,
        "name": clean_name,
    }


def update_bpmn_element(
    xml: str,
    element_id: str,
    name: str | None = None,
    documentation: str | None = None,
) -> tuple[str, dict]:
    if name is None and documentation is None:
        raise ValueError("Indica almeno name o documentation da modificare.")

    root = _parse_bpmn_xml(xml)
    element = _find_editable_element(root, element_id)
    before = {
        "id": element_id,
        "type": _local_name(element.tag),
        "name": element.attrib.get("name", ""),
        "documentation": _documentation_text(element),
    }

    if name is not None:
        clean_name = name.strip()
        if clean_name:
            element.set("name", clean_name)
        else:
            element.attrib.pop("name", None)

    if documentation is not None:
        _replace_documentation(element, documentation.strip())

    after = {
        "id": element_id,
        "type": _local_name(element.tag),
        "name": element.attrib.get("name", ""),
        "documentation": _documentation_text(element),
    }

    return _xml_to_string(root), {"before": before, "after": after}


def delete_bpmn_element(xml: str, element_id: str) -> tuple[str, dict]:
    """
    Delete a BPMN element and its related flows, boundary events, references, and diagram metadata.
    
    Parameters:
        xml (str): BPMN XML containing the element to delete.
        element_id (str): ID of the BPMN element to delete.
    
    Returns:
        tuple[str, dict]: Updated BPMN XML and a summary containing the deleted element,
            removed connected flow IDs, and removed boundary-event IDs.
    """
    root = _parse_bpmn_xml(xml)
    element = _find_editable_element(root, element_id)
    element_type = _local_name(element.tag)

    doomed_ids = {element_id}
    if element_type in FLOW_NODE_TYPES:
        # A boundary event cannot outlive the activity it is attached to.
        for boundary in _boundary_events(root):
            if boundary.attrib.get("attachedToRef") == element_id and boundary.attrib.get("id"):
                doomed_ids.add(boundary.attrib["id"])

    removed_flows = []
    if element_type != "sequenceFlow":
        for flow in list(_sequence_flows(root)):
            if flow.attrib.get("sourceRef") in doomed_ids or flow.attrib.get("targetRef") in doomed_ids:
                flow_id = flow.attrib.get("id", "")
                removed_flows.append(flow_id)
                if flow_id:
                    _remove_flow_references(root, flow_id)
                _remove_element(root, flow)

    if element_type == "sequenceFlow":
        _remove_flow_references(root, element_id)
    for doomed in list(root.iter()):
        if doomed.attrib.get("id") in doomed_ids and doomed is not element and _namespace(doomed.tag) == BPMN_NS:
            _remove_element(root, doomed)
    _remove_element(root, element)
    _remove_di_for_elements(root, doomed_ids)

    updated_xml = layout_bpmn_di(_xml_to_string(root))
    return updated_xml, {
        "action": "delete",
        "id": element_id,
        "type": element_type,
        "removed_connected_flows": [flow_id for flow_id in removed_flows if flow_id],
        "removed_boundary_events": sorted(doomed_ids - {element_id}),
    }


def clear_bpmn_process(xml: str) -> tuple[str, dict]:
    root = _parse_bpmn_xml(xml)
    process = _find_process(root)
    removed = []

    for element in list(process):
        if _namespace(element.tag) != BPMN_NS:
            continue

        element_id = element.attrib.get("id", "")
        element_type = _local_name(element.tag)

        if element_type == "process":
            continue

        if element_id:
            removed.append(
                {
                    "id": element_id,
                    "type": element_type,
                    "name": element.attrib.get("name", ""),
                }
            )

        process.remove(element)

    updated_xml = layout_bpmn_di(_xml_to_string(root))
    return updated_xml, {
        "action": "clear_process",
        "removed": removed,
        "removed_count": len(removed),
    }


def clean_bpmn_visual_metadata_artifacts(xml: str) -> tuple[str, dict]:
    root = _parse_bpmn_xml(xml)
    process = _find_process(root)
    removed = []

    for element in list(process):
        if _namespace(element.tag) != BPMN_NS:
            continue

        element_type = _local_name(element.tag)
        if element_type not in CANVAS_METADATA_ARTIFACT_TYPES:
            continue

        element_id = element.attrib.get("id", "")
        if element_id:
            removed.append(
                {
                    "id": element_id,
                    "type": element_type,
                    "name": element.attrib.get("name", ""),
                }
            )
        process.remove(element)

    if removed:
        _remove_di_for_elements(root, {item["id"] for item in removed if item["id"]})

    return _xml_to_string(root), {
        "action": "clean_visual_metadata_artifacts",
        "removed": removed,
        "removed_count": len(removed),
    }


def connect_bpmn_elements(
    xml: str,
    source_id: str,
    target_id: str,
    flow_id: str | None = None,
    name: str | None = None,
) -> tuple[str, dict]:
    root = _parse_bpmn_xml(xml)
    process = _find_process(root)
    source = _find_flow_node(root, source_id)
    target = _find_flow_node(root, target_id)
    clean_flow_id = _unique_element_id(root, flow_id or f"Flow_{source_id}_to_{target_id}")

    flow = ET.Element(
        _bpmn_tag("sequenceFlow"),
        {"id": clean_flow_id, "sourceRef": source_id, "targetRef": target_id},
    )
    if name and name.strip():
        flow.set("name", name.strip())

    process.append(flow)
    _append_reference(source, "outgoing", clean_flow_id)
    _append_reference(target, "incoming", clean_flow_id)

    updated_xml = layout_bpmn_di(_xml_to_string(root))
    return updated_xml, {
        "action": "connect",
        "id": clean_flow_id,
        "sourceRef": source_id,
        "targetRef": target_id,
    }


def reconnect_bpmn_flow(
    xml: str,
    flow_id: str,
    source_id: str | None = None,
    target_id: str | None = None,
) -> tuple[str, dict]:
    if source_id is None and target_id is None:
        raise ValueError("Indica source_id o target_id da modificare.")

    root = _parse_bpmn_xml(xml)
    flow = _find_sequence_flow(root, flow_id)
    old_source_id = flow.attrib.get("sourceRef")
    old_target_id = flow.attrib.get("targetRef")
    new_source_id = source_id or old_source_id
    new_target_id = target_id or old_target_id

    if not new_source_id or not new_target_id:
        raise ValueError("Sequence flow incompleto.")

    new_source = _find_flow_node(root, new_source_id)
    new_target = _find_flow_node(root, new_target_id)

    if old_source_id:
        _remove_reference_from_element(root, old_source_id, "outgoing", flow_id)
    if old_target_id:
        _remove_reference_from_element(root, old_target_id, "incoming", flow_id)

    flow.set("sourceRef", new_source_id)
    flow.set("targetRef", new_target_id)
    _append_reference(new_source, "outgoing", flow_id)
    _append_reference(new_target, "incoming", flow_id)

    updated_xml = layout_bpmn_di(_xml_to_string(root))
    return updated_xml, {
        "action": "reconnect",
        "id": flow_id,
        "before": {"sourceRef": old_source_id, "targetRef": old_target_id},
        "after": {"sourceRef": new_source_id, "targetRef": new_target_id},
    }


def replace_bpmn_xml(xml: str) -> str:
    root = _parse_bpmn_xml(xml)
    if _local_name(root.tag) != "definitions":
        raise ValueError("XML BPMN non valido: root definitions mancante.")

    process_nodes = [
        element
        for element in root.iter()
        if _namespace(element.tag) == BPMN_NS and _local_name(element.tag) == "process"
    ]
    if not process_nodes:
        raise ValueError("XML BPMN non valido: process mancante.")

    return _xml_to_string(root)


def validate_bpmn_xml(xml: str) -> dict:
    root = _parse_bpmn_xml(xml)
    process = _find_process(root)
    element_ids = {
        element.attrib["id"]
        for element in root.iter()
        if _namespace(element.tag) == BPMN_NS and element.attrib.get("id")
    }
    flow_nodes = [
        element
        for element in process
        if _namespace(element.tag) == BPMN_NS and _local_name(element.tag) in FLOW_NODE_TYPES
    ]
    sequence_flows = list(_sequence_flows(root))
    issues = []
    warnings = []

    for flow in sequence_flows:
        source_ref = flow.attrib.get("sourceRef")
        target_ref = flow.attrib.get("targetRef")
        if source_ref not in element_ids:
            issues.append(f"Flow {flow.attrib.get('id')} ha sourceRef non valido: {source_ref}")
        if target_ref not in element_ids:
            issues.append(f"Flow {flow.attrib.get('id')} ha targetRef non valido: {target_ref}")

    if not any(_local_name(element.tag) == "startEvent" for element in flow_nodes):
        warnings.append("Nessuno startEvent presente.")
    if not any(_local_name(element.tag) == "endEvent" for element in flow_nodes):
        warnings.append("Nessun endEvent presente.")
    if not _has_bpmn_di(root):
        warnings.append("Diagram Interchange BPMN mancante: il canvas potrebbe non renderizzare bene.")

    return {
        "valid": not issues,
        "issues": issues,
        "warnings": warnings,
        "counts": {
            "flow_nodes": len(flow_nodes),
            "sequence_flows": len(sequence_flows),
        },
    }


def validate_bpmn_layout(xml: str) -> dict:
    """
    Validate the diagram layout for missing node positions, overlaps, unreadable dimensions, and undrawn sequence flows.
    
    Parameters:
    	xml (str): BPMN XML content to validate.
    
    Returns:
    	dict: A validation report containing validity, issues, warnings, and layout metrics.
    """
    root = _parse_bpmn_xml(xml)
    process = _find_process(root)
    flow_node_ids = [
        element.attrib["id"]
        for element in process
        if _namespace(element.tag) == BPMN_NS
        and _local_name(element.tag) in FLOW_NODE_TYPES
        and element.attrib.get("id")
    ]
    # Boundary events intentionally sit on their host activity's border.
    placed_node_ids = [
        element.attrib["id"]
        for element in process
        if _namespace(element.tag) == BPMN_NS
        and _local_name(element.tag) in FLOW_NODE_TYPES
        and _local_name(element.tag) != "boundaryEvent"
        and element.attrib.get("id")
    ]
    shapes = _shape_bounds(root)
    node_shapes = {element_id: shapes[element_id] for element_id in placed_node_ids if element_id in shapes}
    issues = []
    warnings = []
    missing_shapes = [element_id for element_id in flow_node_ids if element_id not in shapes]

    if missing_shapes:
        issues.append("Alcuni elementi visibili non hanno una posizione nel disegno.")

    overlaps = _overlapping_boxes(node_shapes, margin=LAYOUT_MIN_NODE_GAP)
    if overlaps:
        issues.append("Alcuni elementi del canvas si sovrappongono o sono troppo vicini.")

    diagram_bounds = _diagram_bounds(shapes)
    if diagram_bounds:
        width = diagram_bounds["width"]
        height = diagram_bounds["height"]
        if width > LAYOUT_MAX_READABLE_WIDTH:
            warnings.append("Il disegno e' ancora molto largo: conviene distribuirlo su piu' righe.")
        if width / max(height, 1) > 4.5:
            warnings.append("Il disegno e' troppo orizzontale per essere letto bene a schermo.")

    edge_count = sum(1 for element in root.iter() if _namespace(element.tag) == BPMNDI_NS and _local_name(element.tag) == "BPMNEdge")
    if edge_count < len(list(_sequence_flows(root))):
        issues.append("Alcuni collegamenti non hanno una linea disegnata.")

    return {
        "valid": not issues,
        "issues": issues,
        "warnings": warnings,
        "metrics": {
            "flow_nodes": len(flow_node_ids),
            "positioned_flow_nodes": len(node_shapes),
            "overlap_count": len(overlaps),
            "edge_count": edge_count,
            "bounds": diagram_bounds,
        },
    }


def preview_bpmn_xml_change(current_xml: str, proposed_xml: str) -> dict:
    current_elements = {item["id"]: item for item in list_bpmn_elements(current_xml)}
    proposed_elements = {item["id"]: item for item in list_bpmn_elements(proposed_xml)}

    added = sorted(set(proposed_elements) - set(current_elements))
    removed = sorted(set(current_elements) - set(proposed_elements))
    changed = []

    for element_id in sorted(set(current_elements) & set(proposed_elements)):
        before = current_elements[element_id]
        after = proposed_elements[element_id]
        if before != after:
            changed.append({"id": element_id, "before": before, "after": after})

    return {
        "added": [proposed_elements[element_id] for element_id in added],
        "removed": [current_elements[element_id] for element_id in removed],
        "changed": changed,
        "validation": validate_bpmn_xml(proposed_xml),
    }


def optimize_bpmn_layout(xml: str) -> tuple[str, dict]:
    if _has_collaboration(_parse_bpmn_xml(xml)):
        report = validate_bpmn_layout(xml)
        return xml, {
            "valid": bool(report.get("valid")),
            "selected_score": _layout_score(report),
            "selected_report": report,
            "attempts": [],
            "skipped": "collaboration_layout_owned_by_semantic_serializer",
        }

    strategies = [
        BpmnLayoutConfig(max_nodes_per_row=5, column_gap=320, row_gap=190, lane_row_height=190),
        BpmnLayoutConfig(max_nodes_per_row=4, column_gap=330, row_gap=205, lane_row_height=200),
        BpmnLayoutConfig(max_nodes_per_row=3, column_gap=340, row_gap=220, lane_row_height=210),
        BpmnLayoutConfig(max_nodes_per_row=4, column_gap=360, row_gap=230, lane_row_height=220, annotation_columns=3),
    ]
    attempts = []
    best_xml = ""
    best_report: dict | None = None
    best_score: float | None = None

    for index, config in enumerate(strategies, start=1):
        candidate_xml = layout_bpmn_di(xml, config=config)
        report = validate_bpmn_layout(candidate_xml)
        score = _layout_score(report)
        attempts.append(
            {
                "attempt": index,
                "config": asdict(config),
                "valid": report.get("valid"),
                "score": score,
                "report": report,
            }
        )

        if best_score is None or score < best_score:
            best_xml = candidate_xml
            best_report = report
            best_score = score

        if report.get("valid") and not report.get("warnings"):
            break

    return best_xml, {
        "valid": bool(best_report and best_report.get("valid")),
        "selected_score": best_score,
        "selected_report": best_report or {},
        "attempts": attempts,
    }


def layout_bpmn_di(xml: str, config: BpmnLayoutConfig | None = None) -> str:
    """
    Generate BPMN diagram interchange metadata for the process.
    
    Parameters:
    	xml (str): BPMN XML containing a process.
    	config (BpmnLayoutConfig | None): Optional layout configuration.
    
    Returns:
    	str: BPMN XML with regenerated diagram, shape, and edge layout metadata.
    """
    config = config or BpmnLayoutConfig()
    root = _parse_bpmn_xml(xml)
    definitions_id = root.attrib.get("id", "Definitions")
    process = _find_process(root)
    process_id = process.attrib.get("id", "Process")
    collaboration = _find_collaboration(root)
    plane_element = (
        collaboration.attrib.get("id", process_id) if collaboration is not None else process_id
    )

    for child in list(root):
        if _namespace(child.tag) == BPMNDI_NS and _local_name(child.tag) == "BPMNDiagram":
            root.remove(child)

    diagram = ET.SubElement(root, _bpmndi_tag("BPMNDiagram"), {"id": f"{definitions_id}_Diagram"})
    plane = ET.SubElement(
        diagram,
        _bpmndi_tag("BPMNPlane"),
        {
            "id": f"{process_id}_Plane",
            "bpmnElement": plane_element,
        },
    )

    all_flow_nodes = [
        element
        for element in process
        if _namespace(element.tag) == BPMN_NS and _local_name(element.tag) in FLOW_NODE_TYPES and element.attrib.get("id")
    ]
    flow_nodes = [e for e in all_flow_nodes if _local_name(e.tag) != "boundaryEvent"]
    boundary_nodes = [e for e in all_flow_nodes if _local_name(e.tag) == "boundaryEvent"]
    lane_shapes = _layout_lane_shapes(process, flow_nodes, config)
    for lane_shape in lane_shapes:
        shape = ET.SubElement(
            plane,
            _bpmndi_tag("BPMNShape"),
            {
                "id": f"{lane_shape['id']}_di",
                "bpmnElement": lane_shape["id"],
                "isHorizontal": "true",
            },
        )
        ET.SubElement(
            shape,
            _dc_tag("Bounds"),
            {
                "x": str(lane_shape["x"]),
                "y": str(lane_shape["y"]),
                "width": str(lane_shape["width"]),
                "height": str(lane_shape["height"]),
            },
        )

    node_positions = _layout_flow_nodes(process, flow_nodes, config)
    for element in flow_nodes:
        element_type = _local_name(element.tag)
        element_id = element.attrib.get("id")
        if not element_id:
            continue

        position = node_positions[element_id]
        shape = ET.SubElement(
            plane,
            _bpmndi_tag("BPMNShape"),
            {"id": f"{element_id}_di", "bpmnElement": element_id},
        )
        ET.SubElement(
            shape,
            _dc_tag("Bounds"),
            {
                "x": str(position["x"]),
                "y": str(position["y"]),
                "width": str(position["width"]),
                "height": str(position["height"]),
            },
        )

    for element in boundary_nodes:
        element_id = element.attrib["id"]
        host = node_positions.get(element.attrib.get("attachedToRef"))
        if host is not None:
            position = {
                "x": host["x"] + host["width"] * 0.62,
                "y": host["y"] + host["height"] - 18,
                "width": 36,
                "height": 36,
            }
        else:
            position = {"x": LAYOUT_LEFT, "y": LAYOUT_TOP, "width": 36, "height": 36}
        node_positions[element_id] = position
        shape = ET.SubElement(
            plane,
            _bpmndi_tag("BPMNShape"),
            {"id": f"{element_id}_di", "bpmnElement": element_id},
        )
        ET.SubElement(
            shape,
            _dc_tag("Bounds"),
            {
                "x": str(position["x"]),
                "y": str(position["y"]),
                "width": str(position["width"]),
                "height": str(position["height"]),
            },
        )

    artifact_positions = _layout_artifacts(process, node_positions, config)
    for element_id, position in artifact_positions.items():
        shape = ET.SubElement(
            plane,
            _bpmndi_tag("BPMNShape"),
            {"id": f"{element_id}_di", "bpmnElement": element_id},
        )
        ET.SubElement(
            shape,
            _dc_tag("Bounds"),
            {
                "x": str(position["x"]),
                "y": str(position["y"]),
                "width": str(position["width"]),
                "height": str(position["height"]),
            },
        )

    for flow in _sequence_flows(root):
        flow_id = flow.attrib.get("id")
        source = node_positions.get(flow.attrib.get("sourceRef"))
        target = node_positions.get(flow.attrib.get("targetRef"))
        if not flow_id or not source or not target:
            continue

        edge = ET.SubElement(
            plane,
            _bpmndi_tag("BPMNEdge"),
            {"id": f"{flow_id}_di", "bpmnElement": flow_id},
        )
        ET.SubElement(
            edge,
            _di_tag("waypoint"),
            {"x": str(source["x"] + source["width"]), "y": str(source["y"] + source["height"] / 2)},
        )
        for point in _edge_waypoints(source, target)[1:]:
            ET.SubElement(edge, _di_tag("waypoint"), {"x": str(point["x"]), "y": str(point["y"])})

    connectable_positions = {**node_positions, **artifact_positions}
    for association in _associations(root):
        association_id = association.attrib.get("id")
        source = connectable_positions.get(association.attrib.get("sourceRef"))
        target = connectable_positions.get(association.attrib.get("targetRef"))
        if not association_id or not source or not target:
            continue

        edge = ET.SubElement(
            plane,
            _bpmndi_tag("BPMNEdge"),
            {"id": f"{association_id}_di", "bpmnElement": association_id},
        )
        ET.SubElement(
            edge,
            _di_tag("waypoint"),
            {"x": str(source["x"] + source["width"] / 2), "y": str(source["y"] + source["height"])},
        )
        ET.SubElement(
            edge,
            _di_tag("waypoint"),
            {"x": str(target["x"] + target["width"] / 2), "y": str(target["y"])},
        )

    if collaboration is not None:
        pool_positions = _layout_participant_shapes(
            plane, collaboration, process_id, node_positions, lane_shapes
        )
        _layout_message_flow_edges(plane, collaboration, {**node_positions, **pool_positions})

    return _xml_to_string(root)


def _layout_flow_nodes(
    process: ET.Element,
    flow_nodes: list[ET.Element],
    config: BpmnLayoutConfig,
) -> dict[str, dict[str, float]]:
    lane_y_by_id = _lane_y_by_id(process, flow_nodes, config)
    positions: dict[str, dict[str, float]] = {}

    for rank, element in enumerate(flow_nodes):
        element_id = element.attrib["id"]
        element_type = _local_name(element.tag)
        width, height = _shape_size(element_type)
        row = rank // config.max_nodes_per_row
        column = rank % config.max_nodes_per_row
        lane_id = _lane_id_for_node(process, element_id)
        lane_base_y = lane_y_by_id.get(lane_id or "", LAYOUT_TOP)
        x = LAYOUT_LEFT + LAYOUT_LANE_LABEL_WIDTH + 70 + column * config.column_gap
        y = lane_base_y + 56 + row * config.row_gap + (config.lane_row_height - height) / 2
        positions[element_id] = {"x": x, "y": y, "width": width, "height": height}

    return positions


def _layout_lane_shapes(
    process: ET.Element,
    flow_nodes: list[ET.Element],
    config: BpmnLayoutConfig,
) -> list[dict[str, float | str]]:
    lanes = _lanes(process)
    if not lanes:
        return []

    rows = max(1, (len(flow_nodes) + config.max_nodes_per_row - 1) // config.max_nodes_per_row)
    lane_height = 80 + rows * config.row_gap
    lane_width = LAYOUT_LANE_LABEL_WIDTH + 120 + min(len(flow_nodes), config.max_nodes_per_row) * config.column_gap
    lane_width = max(980, min(LAYOUT_MAX_READABLE_WIDTH, lane_width))
    return [
        {
            "id": lane.attrib["id"],
            "x": LAYOUT_LEFT,
            "y": LAYOUT_TOP + index * lane_height,
            "width": lane_width,
            "height": lane_height,
        }
        for index, lane in enumerate(lanes)
        if lane.attrib.get("id")
    ]


def _layout_artifacts(
    process: ET.Element,
    node_positions: dict[str, dict[str, float]],
    config: BpmnLayoutConfig,
) -> dict[str, dict[str, float]]:
    positions: dict[str, dict[str, float]] = {}
    data_by_source_count: dict[str, int] = {}
    associations_by_target = {
        association.attrib.get("targetRef"): association.attrib.get("sourceRef")
        for association in _associations(process)
        if association.attrib.get("targetRef")
    }

    annotations = [
        element
        for element in process
        if _namespace(element.tag) == BPMN_NS and _local_name(element.tag) in ANNOTATION_TYPES and element.attrib.get("id")
    ]
    for index, element in enumerate(annotations):
        row = index // config.annotation_columns
        column = index % config.annotation_columns
        positions[element.attrib["id"]] = {
            "x": LAYOUT_LEFT + LAYOUT_LANE_LABEL_WIDTH + 70 + column * 330,
            "y": 44 + row * 108,
            "width": 260,
            "height": 82,
        }

    data_objects = [
        element
        for element in process
        if _namespace(element.tag) == BPMN_NS and _local_name(element.tag) in DATA_ARTIFACT_TYPES and element.attrib.get("id")
    ]
    for index, element in enumerate(data_objects):
        element_id = element.attrib["id"]
        source_id = associations_by_target.get(element_id) or next(iter(node_positions), "")
        source = node_positions.get(source_id)
        if source:
            offset = data_by_source_count.get(source_id, 0)
            data_by_source_count[source_id] = offset + 1
            x = source["x"] + 12 + offset * 78
            y = source["y"] + source["height"] + 34
        else:
            row = index // 6
            column = index % 6
            x = LAYOUT_LEFT + LAYOUT_LANE_LABEL_WIDTH + 70 + column * 120
            y = LAYOUT_TOP + 90 + row * 90
        positions[element_id] = {"x": x, "y": y, "width": 72, "height": 58}

    return positions


def _edge_waypoints(source: dict[str, float], target: dict[str, float]) -> list[dict[str, float]]:
    start = {"x": source["x"] + source["width"], "y": source["y"] + source["height"] / 2}
    end = {"x": target["x"], "y": target["y"] + target["height"] / 2}

    if target["x"] > source["x"] and abs(start["y"] - end["y"]) < 2:
        return [start, end]

    if target["x"] > source["x"]:
        mid_x = start["x"] + max(70, (end["x"] - start["x"]) / 2)
        return [start, {"x": mid_x, "y": start["y"]}, {"x": mid_x, "y": end["y"]}, end]

    route_y = max(source["y"] + source["height"], target["y"] + target["height"]) + 58
    return [
        start,
        {"x": start["x"] + 68, "y": start["y"]},
        {"x": start["x"] + 68, "y": route_y},
        {"x": end["x"] - 68, "y": route_y},
        {"x": end["x"] - 68, "y": end["y"]},
        end,
    ]


def _layout_score(report: dict) -> float:
    metrics = report.get("metrics") or {}
    bounds = metrics.get("bounds") or {}
    width = float(bounds.get("width") or 0)
    height = float(bounds.get("height") or 1)
    aspect_ratio = width / max(height, 1)
    score = 0.0
    score += len(report.get("issues") or []) * 1000
    score += len(report.get("warnings") or []) * 100
    score += float(metrics.get("overlap_count") or 0) * 500
    score += max(0.0, width - LAYOUT_MAX_READABLE_WIDTH) / 10
    score += max(0.0, aspect_ratio - 4.5) * 80
    score += max(0.0, 2.0 - aspect_ratio) * 12
    score += max(0.0, height - 1400) / 20
    return score


def _lane_y_by_id(
    process: ET.Element,
    flow_nodes: list[ET.Element],
    config: BpmnLayoutConfig,
) -> dict[str, float]:
    lanes = _lanes(process)
    if not lanes:
        return {}

    rows = max(1, (len(flow_nodes) + config.max_nodes_per_row - 1) // config.max_nodes_per_row)
    lane_height = 80 + rows * config.row_gap
    return {
        lane.attrib["id"]: LAYOUT_TOP + index * lane_height
        for index, lane in enumerate(lanes)
        if lane.attrib.get("id")
    }


def _lanes(process: ET.Element) -> list[ET.Element]:
    return [
        element
        for element in process.iter()
        if _namespace(element.tag) == BPMN_NS and _local_name(element.tag) == "lane" and element.attrib.get("id")
    ]


def _lane_id_for_node(process: ET.Element, element_id: str) -> str | None:
    for lane in _lanes(process):
        for child in lane:
            if _namespace(child.tag) == BPMN_NS and _local_name(child.tag) == "flowNodeRef":
                if (child.text or "").strip() == element_id:
                    return lane.attrib.get("id")

    return None


def _shape_bounds(root: ET.Element) -> dict[str, dict[str, float]]:
    bounds_by_element = {}

    for shape in root.iter():
        if _namespace(shape.tag) != BPMNDI_NS or _local_name(shape.tag) != "BPMNShape":
            continue
        bpmn_element = shape.attrib.get("bpmnElement")
        if not bpmn_element:
            continue
        bounds = next(
            (
                child
                for child in shape
                if _namespace(child.tag) == DC_NS and _local_name(child.tag) == "Bounds"
            ),
            None,
        )
        if bounds is None:
            continue
        try:
            bounds_by_element[bpmn_element] = {
                "x": float(bounds.attrib.get("x", 0)),
                "y": float(bounds.attrib.get("y", 0)),
                "width": float(bounds.attrib.get("width", 0)),
                "height": float(bounds.attrib.get("height", 0)),
            }
        except ValueError:
            continue

    return bounds_by_element


def _diagram_bounds(shapes: dict[str, dict[str, float]]) -> dict[str, float] | None:
    if not shapes:
        return None

    min_x = min(item["x"] for item in shapes.values())
    min_y = min(item["y"] for item in shapes.values())
    max_x = max(item["x"] + item["width"] for item in shapes.values())
    max_y = max(item["y"] + item["height"] for item in shapes.values())
    return {"x": min_x, "y": min_y, "width": max_x - min_x, "height": max_y - min_y}


def _overlapping_boxes(boxes: dict[str, dict[str, float]], margin: float) -> list[tuple[str, str]]:
    ids = list(boxes)
    overlaps = []

    for index, left_id in enumerate(ids):
        left = boxes[left_id]
        for right_id in ids[index + 1 :]:
            right = boxes[right_id]
            if (
                left["x"] < right["x"] + right["width"] + margin
                and left["x"] + left["width"] + margin > right["x"]
                and left["y"] < right["y"] + right["height"] + margin
                and left["y"] + left["height"] + margin > right["y"]
            ):
                overlaps.append((left_id, right_id))

    return overlaps


def _parse_bpmn_xml(xml: str) -> ET.Element:
    clean_xml = xml.strip()
    if not clean_xml:
        raise ValueError("XML BPMN vuoto.")

    try:
        return ET.fromstring(clean_xml)
    except ET.ParseError as exc:
        raise ValueError(f"XML BPMN non valido: {exc}") from exc


def _find_editable_element(root: ET.Element, element_id: str) -> ET.Element:
    for element in root.iter():
        if element.attrib.get("id") != element_id:
            continue
        if _namespace(element.tag) == BPMN_NS and _local_name(element.tag) in EDITABLE_BPMN_TYPES:
            return element

    raise ValueError(f"Elemento BPMN modificabile non trovato: {element_id}")


def _find_process(root: ET.Element) -> ET.Element:
    for element in root.iter():
        if _namespace(element.tag) == BPMN_NS and _local_name(element.tag) == "process":
            return element

    raise ValueError("XML BPMN non valido: process mancante.")


def _find_flow_node(root: ET.Element, element_id: str) -> ET.Element:
    element = _find_editable_element(root, element_id)
    if _local_name(element.tag) not in FLOW_NODE_TYPES:
        raise ValueError(f"Elemento non collegabile come flow node: {element_id}")
    return element


def _find_sequence_flow(root: ET.Element, flow_id: str) -> ET.Element:
    element = _find_editable_element(root, flow_id)
    if _local_name(element.tag) != "sequenceFlow":
        raise ValueError(f"Elemento non e' un sequenceFlow: {flow_id}")
    return element


def _sequence_flows(root: ET.Element) -> list[ET.Element]:
    return [
        element
        for element in root.iter()
        if _namespace(element.tag) == BPMN_NS and _local_name(element.tag) == "sequenceFlow"
    ]


def _associations(root: ET.Element) -> list[ET.Element]:
    """Return all BPMN association elements in the XML tree.
    
    Parameters:
    	root (ET.Element): Root element of the BPMN XML tree.
    
    Returns:
    	list[ET.Element]: BPMN association elements found in the tree.
    """
    return [
        element
        for element in root.iter()
        if _namespace(element.tag) == BPMN_NS and _local_name(element.tag) == "association"
    ]


def _boundary_events(root: ET.Element) -> list[ET.Element]:
    """Find all boundary event elements in the BPMN document.
    
    Returns:
    	list[ET.Element]: Boundary event elements found in the document.
    """
    return [
        element
        for element in root.iter()
        if _namespace(element.tag) == BPMN_NS and _local_name(element.tag) == "boundaryEvent"
    ]


def _find_collaboration(root: ET.Element) -> ET.Element | None:
    """Find the collaboration element in a BPMN XML tree.
    
    Parameters:
    	root (ET.Element): Root element of the BPMN XML tree.
    
    Returns:
    	ET.Element | None: The collaboration element, or `None` if the tree does not contain one.
    """
    return next(
        (
            element
            for element in root.iter()
            if _namespace(element.tag) == BPMN_NS and _local_name(element.tag) == "collaboration"
        ),
        None,
    )


def _message_flows(collaboration: ET.Element) -> list[ET.Element]:
    return [
        element
        for element in collaboration
        if _namespace(element.tag) == BPMN_NS and _local_name(element.tag) == "messageFlow"
    ]


def _layout_participant_shapes(
    plane: ET.Element,
    collaboration: ET.Element,
    process_id: str,
    node_positions: dict[str, dict[str, float]],
    lane_shapes: list[dict[str, float | str]],
) -> dict[str, dict[str, float]]:
    boxes: list[dict[str, float]] = [
        {"x": float(shape["x"]), "y": float(shape["y"]), "width": float(shape["width"]), "height": float(shape["height"])}
        for shape in lane_shapes
    ]
    boxes.extend(node_positions.values())
    if boxes:
        min_x = min(box["x"] for box in boxes)
        min_y = min(box["y"] for box in boxes)
        max_x = max(box["x"] + box["width"] for box in boxes)
        max_y = max(box["y"] + box["height"] for box in boxes)
    else:
        min_x, min_y, max_x, max_y = float(LAYOUT_LEFT), float(LAYOUT_TOP), 1000.0, 400.0

    participants = [
        element
        for element in collaboration
        if _namespace(element.tag) == BPMN_NS and _local_name(element.tag) == "participant"
    ]
    pool_left = min_x - 30
    pool_width = (max_x - pool_left) + 40
    primary_top = min_y - 30
    primary_height = max(max_y - primary_top + 30, 160.0)

    positions: dict[str, dict[str, float]] = {}
    external_top = primary_top + primary_height + 40
    for participant in participants:
        participant_id = participant.attrib.get("id")
        if not participant_id:
            continue
        if participant.attrib.get("processRef") == process_id:
            box = {"x": pool_left, "y": primary_top, "width": pool_width, "height": primary_height}
        else:
            box = {"x": pool_left, "y": external_top, "width": pool_width, "height": 120.0}
            external_top += 160
        positions[participant_id] = box
        shape = ET.SubElement(
            plane,
            _bpmndi_tag("BPMNShape"),
            {"id": f"{participant_id}_di", "bpmnElement": participant_id, "isHorizontal": "true"},
        )
        ET.SubElement(
            shape,
            _dc_tag("Bounds"),
            {"x": str(box["x"]), "y": str(box["y"]), "width": str(box["width"]), "height": str(box["height"])},
        )
    return positions


def _layout_message_flow_edges(
    plane: ET.Element,
    collaboration: ET.Element,
    endpoint_positions: dict[str, dict[str, float]],
) -> None:
    for message_flow in _message_flows(collaboration):
        flow_id = message_flow.attrib.get("id")
        source = endpoint_positions.get(message_flow.attrib.get("sourceRef"))
        target = endpoint_positions.get(message_flow.attrib.get("targetRef"))
        if not flow_id or not source or not target:
            continue

        start_x = source["x"] + source["width"] / 2
        end_x = target["x"] + target["width"] / 2
        if source["y"] <= target["y"]:
            start_y, end_y = source["y"] + source["height"], target["y"]
        else:
            start_y, end_y = source["y"], target["y"] + target["height"]

        edge = ET.SubElement(
            plane,
            _bpmndi_tag("BPMNEdge"),
            {"id": f"{flow_id}_di", "bpmnElement": flow_id},
        )
        ET.SubElement(edge, _di_tag("waypoint"), {"x": str(start_x), "y": str(start_y)})
        ET.SubElement(edge, _di_tag("waypoint"), {"x": str(end_x), "y": str(end_y)})


def _remove_element(root: ET.Element, target: ET.Element) -> None:
    for parent in root.iter():
        for child in list(parent):
            if child is target:
                parent.remove(child)
                return

    raise ValueError("Elemento BPMN non rimosso.")


def _remove_di_for_elements(root: ET.Element, element_ids: set[str]) -> None:
    if not element_ids:
        return

    for parent in root.iter():
        for child in list(parent):
            if _namespace(child.tag) != BPMNDI_NS:
                continue
            if _local_name(child.tag) not in {"BPMNShape", "BPMNEdge"}:
                continue
            if child.attrib.get("bpmnElement") in element_ids:
                parent.remove(child)


def _remove_flow_references(root: ET.Element, element_id: str) -> None:
    for element in root.iter():
        if _namespace(element.tag) != BPMN_NS:
            continue
        for child in list(element):
            if _local_name(child.tag) in {"incoming", "outgoing"} and (child.text or "").strip() == element_id:
                element.remove(child)


def _append_reference(element: ET.Element, ref_type: str, flow_id: str) -> None:
    for child in element:
        if _local_name(child.tag) == ref_type and (child.text or "").strip() == flow_id:
            return

    reference = ET.Element(_bpmn_tag(ref_type))
    reference.text = flow_id
    element.append(reference)


def _remove_reference_from_element(root: ET.Element, element_id: str, ref_type: str, flow_id: str) -> None:
    element = _find_editable_element(root, element_id)
    for child in list(element):
        if _local_name(child.tag) == ref_type and (child.text or "").strip() == flow_id:
            element.remove(child)


def _ensure_lane_set(process: ET.Element) -> ET.Element:
    for child in process:
        if _namespace(child.tag) == BPMN_NS and _local_name(child.tag) == "laneSet":
            return child

    lane_set = ET.Element(_bpmn_tag("laneSet"), {"id": _unique_element_id(process, "LaneSet")})
    process.insert(0, lane_set)
    return lane_set


def _unique_element_id(root: ET.Element, base_id: str) -> str:
    clean_base = "".join(char if char.isalnum() or char == "_" else "_" for char in base_id.strip())
    clean_base = clean_base or "Element"
    existing_ids = {
        element.attrib["id"]
        for element in root.iter()
        if element.attrib.get("id")
    }
    candidate = clean_base
    suffix = 2
    while candidate in existing_ids:
        candidate = f"{clean_base}_{suffix}"
        suffix += 1
    return candidate


def _default_element_id(element_type: str, name: str) -> str:
    clean_name = "".join(char if char.isalnum() else "_" for char in name.strip().title()).strip("_")
    return f"{element_type}_{clean_name or 'New'}"


def _shape_size(element_type: str) -> tuple[int, int]:
    if element_type in {"startEvent", "endEvent", "intermediateCatchEvent", "intermediateThrowEvent"}:
        return 36, 36
    if element_type.endswith("Gateway"):
        return 50, 50
    return 110, 80


def _has_bpmn_di(root: ET.Element) -> bool:
    return any(
        _namespace(element.tag) == BPMNDI_NS and _local_name(element.tag) == "BPMNDiagram"
        for element in root.iter()
    )


def _has_collaboration(root: ET.Element) -> bool:
    return any(
        _namespace(element.tag) == BPMN_NS and _local_name(element.tag) == "collaboration"
        for element in root.iter()
    )


def _bpmn_tag(local_name: str) -> str:
    return f"{{{BPMN_NS}}}{local_name}"


def _bpmndi_tag(local_name: str) -> str:
    return f"{{{BPMNDI_NS}}}{local_name}"


def _dc_tag(local_name: str) -> str:
    return f"{{{DC_NS}}}{local_name}"


def _di_tag(local_name: str) -> str:
    return f"{{{DI_NS}}}{local_name}"


def _replace_documentation(element: ET.Element, text: str) -> None:
    doc_tag = f"{{{BPMN_NS}}}documentation"

    for child in list(element):
        if child.tag == doc_tag:
            element.remove(child)

    if not text:
        return

    documentation = ET.Element(doc_tag)
    documentation.text = text
    element.insert(0, documentation)


def _documentation_text(element: ET.Element) -> str:
    doc_tag = f"{{{BPMN_NS}}}documentation"
    return "\n".join(
        (child.text or "").strip()
        for child in element
        if child.tag == doc_tag and (child.text or "").strip()
    )


def _xml_to_string(root: ET.Element) -> str:
    return ET.tostring(root, encoding="unicode")


def _namespace(tag: str) -> str:
    if tag.startswith("{"):
        return tag[1:].split("}", 1)[0]
    return ""


def _local_name(tag: str) -> str:
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag
