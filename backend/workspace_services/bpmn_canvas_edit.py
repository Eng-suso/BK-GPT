from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from collections.abc import Iterable
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
# Data objects / stores and their read-write associations are part of the
# operating view and stay on the canvas. Only free-text annotations (and the
# associations that dock to them) are canvas-only noise that belongs in the
# semantic payload instead.
CANVAS_METADATA_ARTIFACT_TYPES = ANNOTATION_TYPES

LAYOUT_LEFT = 140
LAYOUT_TOP = 190
LAYOUT_LANE_LABEL_WIDTH = 88
LAYOUT_COLUMN_GAP = 230
LAYOUT_ROW_GAP = 190
LAYOUT_LANE_ROW_HEIGHT = 210
LAYOUT_MAX_NODES_PER_ROW = 6
LAYOUT_MIN_NODE_GAP = 48
LAYOUT_MAX_READABLE_WIDTH = 1900


@dataclass(frozen=True)
class BpmnLayoutConfig:
    max_nodes_per_row: int = LAYOUT_MAX_NODES_PER_ROW
    column_gap: int = LAYOUT_COLUMN_GAP
    row_gap: int = LAYOUT_ROW_GAP
    lane_row_height: int = LAYOUT_LANE_ROW_HEIGHT
    annotation_columns: int = 4


def _readable_layout_config(config: BpmnLayoutConfig) -> BpmnLayoutConfig:
    """Keep every planned column inside the maximum readable lane width."""
    available = LAYOUT_MAX_READABLE_WIDTH - LAYOUT_LANE_LABEL_WIDTH - 190
    max_columns = max(2, int(available // config.column_gap))
    if config.max_nodes_per_row <= max_columns:
        return config
    return replace(config, max_nodes_per_row=max_columns)


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
    """Strip canvas-only annotation noise: free-text annotations and the
    associations that dock to them. The data perspective (data objects, data
    stores and their read/write associations) stays on the canvas.
    """
    root = _parse_bpmn_xml(xml)
    process = _find_process(root)
    removed = []

    annotation_ids = {
        element.attrib["id"]
        for element in process
        if _namespace(element.tag) == BPMN_NS
        and _local_name(element.tag) in ANNOTATION_TYPES
        and element.attrib.get("id")
    }

    for element in list(process):
        if _namespace(element.tag) != BPMN_NS:
            continue

        element_type = _local_name(element.tag)
        docks_to_annotation = element_type == "association" and (
            element.attrib.get("sourceRef") in annotation_ids
            or element.attrib.get("targetRef") in annotation_ids
        )
        if element_type not in CANVAS_METADATA_ARTIFACT_TYPES and not docks_to_annotation:
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

    artifact_ids = {
        element.attrib["id"]
        for element in process
        if _namespace(element.tag) == BPMN_NS
        and _local_name(element.tag) in DATA_ARTIFACT_TYPES
        and element.attrib.get("id")
    }
    visible_shapes = {
        element_id: bounds
        for element_id, bounds in shapes.items()
        if element_id in node_shapes or element_id in artifact_ids
    }
    artifact_overlaps = [
        pair for pair in _overlapping_boxes(visible_shapes, margin=4)
        if artifact_ids.intersection(pair)
    ]
    if artifact_overlaps:
        issues.append("Documenti o archivi si sovrappongono ad altri elementi del canvas.")

    edge_shape_crossings = _edge_shape_crossings(
        root, {node_id: shapes[node_id] for node_id in flow_node_ids if node_id in shapes}
    )
    if edge_shape_crossings:
        warnings.append("Alcuni collegamenti attraversano attivita' o gateway e rendono il disegno difficile da leggere.")
    edge_edge_crossings = _edge_edge_crossings(root)
    if edge_edge_crossings:
        warnings.append("Alcune linee del disegno si incrociano o si sovrappongono.")

    diagram_bounds = _diagram_bounds(shapes)
    if diagram_bounds:
        width = diagram_bounds["width"]
        height = diagram_bounds["height"]
        gateway_count = sum(
            _local_name(element.tag).endswith("Gateway") for element in process
            if _namespace(element.tag) == BPMN_NS
        )
        compact_simple_process = len(flow_node_ids) <= 12 and gateway_count < 3
        if width > LAYOUT_MAX_READABLE_WIDTH and compact_simple_process:
            warnings.append("Il disegno e' ancora molto largo: conviene distribuirlo su piu' righe.")
        if width / max(height, 1) > 4.5 and compact_simple_process:
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
            "artifact_overlap_count": len(artifact_overlaps),
            "edge_shape_crossing_count": len(edge_shape_crossings),
            "edge_edge_crossing_count": len(edge_edge_crossings),
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


def optimize_bpmn_layout(
    xml: str,
    config: BpmnLayoutConfig | None = None,
    planned_rows: list[list[str]] | None = None,
    require_planned_rows: bool = False,
) -> tuple[str, dict]:
    if require_planned_rows and planned_rows is None:
        raise ValueError("Il layout BPMN richiede planned_rows esplicite dal layout consultant agent.")
    layout_config = _readable_layout_config(config or BpmnLayoutConfig())
    updated_xml = layout_bpmn_di(xml, config=layout_config, planned_rows=planned_rows)
    report = validate_bpmn_layout(updated_xml)
    score = _layout_score(report)

    return updated_xml, {
        "valid": bool(report.get("valid")),
        "selected_score": score,
        "selected_report": report,
        "attempts": [
            {
                "attempt": 1,
                "config": asdict(layout_config),
                "valid": report.get("valid"),
                "score": score,
                "report": report,
            }
        ],
    }


def _append_node_label(
    shape: ET.Element,
    element_type: str,
    name: str,
    position: dict[str, float],
) -> None:
    if not name.strip():
        return
    width = min(180.0, max(110.0, len(name) * 5.8))
    height = 44.0 if len(name) > 28 else 30.0
    if element_type == "boundaryEvent":
        x = position["x"] + position["width"] + 14
        y = position["y"] + 4
    else:
        x = position["x"] + position["width"] / 2 - width / 2
        y = position["y"] - height - 12
    label = ET.SubElement(shape, _bpmndi_tag("BPMNLabel"))
    ET.SubElement(label, _dc_tag("Bounds"), {
        "x": str(x), "y": str(y), "width": str(width), "height": str(height),
    })


def layout_bpmn_di(
    xml: str,
    config: BpmnLayoutConfig | None = None,
    planned_rows: list[list[str]] | None = None,
) -> str:
    """
    Generate BPMN diagram interchange metadata for the process.
    
    Parameters:
    	xml (str): BPMN XML containing a process.
    	config (BpmnLayoutConfig | None): Optional layout configuration.
    
    Returns:
    	str: BPMN XML with regenerated diagram, shape, and edge layout metadata.
    """
    config = _readable_layout_config(config or BpmnLayoutConfig())
    root = _parse_bpmn_xml(xml)
    _normalize_connector_labels(root)
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
    lane_shapes = _layout_lane_shapes(process, flow_nodes, config, planned_rows=planned_rows)
    for lane_shape in lane_shapes:
        lane_id = str(lane_shape["id"])
        shape = ET.SubElement(
            plane,
            _bpmndi_tag("BPMNShape"),
            {
                "id": f"{lane_id}_di",
                "bpmnElement": lane_id,
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

    node_positions = _layout_flow_nodes(process, flow_nodes, config, planned_rows=planned_rows)
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
        if element_type.endswith("Gateway") or element_type == "endEvent":
            _append_node_label(shape, element_type, element.attrib.get("name", ""), position)

    for element in boundary_nodes:
        element_id = element.attrib["id"]
        attached_to_ref = element.attrib.get("attachedToRef")
        host = node_positions.get(attached_to_ref) if attached_to_ref else None
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
        _append_node_label(shape, "boundaryEvent", element.attrib.get("name", ""), position)

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

    connectable_positions = {**node_positions, **artifact_positions}
    boundary_ids = {element.attrib["id"] for element in boundary_nodes}
    outgoing_index: dict[str, int] = {}
    for flow in _sequence_flows(root):
        flow_id = flow.attrib.get("id")
        source_ref = flow.attrib.get("sourceRef")
        target_ref = flow.attrib.get("targetRef")
        source = node_positions.get(source_ref) if source_ref else None
        target = node_positions.get(target_ref) if target_ref else None
        if not flow_id or source is None or target is None:
            continue

        edge = ET.SubElement(
            plane,
            _bpmndi_tag("BPMNEdge"),
            {"id": f"{flow_id}_di", "bpmnElement": flow_id},
        )
        source_index = outgoing_index.get(source_ref, 0)
        outgoing_index[source_ref] = source_index + 1
        points = _edge_waypoints(
            source, target, connectable_positions.values(), source_index,
            source_ref in boundary_ids,
        )
        for point in points:
            ET.SubElement(edge, _di_tag("waypoint"), {"x": str(point["x"]), "y": str(point["y"])})
        if flow.attrib.get("name") and len(points) >= 3:
            vertical = max((abs(a["y"] - b["y"]) for a, b in zip(points, points[1:])), default=0)
            horizontal = max((abs(a["x"] - b["x"]) for a, b in zip(points, points[1:])), default=0)
            if vertical > 150 and vertical > horizontal:
                label = ET.SubElement(edge, _bpmndi_tag("BPMNLabel"))
                ET.SubElement(label, _dc_tag("Bounds"), {
                    "x": str(points[-2]["x"] + 14),
                    "y": str(target["y"] - 32),
                    "width": "125", "height": "28",
                })

    for association in _associations(root):
        association_id = association.attrib.get("id")
        source_ref = association.attrib.get("sourceRef")
        target_ref = association.attrib.get("targetRef")
        source = connectable_positions.get(source_ref) if source_ref else None
        target = connectable_positions.get(target_ref) if target_ref else None
        if not association_id or source is None or target is None:
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

    _avoid_node_label_collisions(plane, connectable_positions, lane_shapes)
    return _xml_to_string(root)


def _normalize_connector_labels(root: ET.Element) -> None:
    """Only gateway branches carry visible names on connectors."""
    gateways = {
        element.attrib["id"] for element in root.iter()
        if _namespace(element.tag) == BPMN_NS
        and _local_name(element.tag).endswith("Gateway")
        and element.attrib.get("id")
    }
    for flow in _sequence_flows(root):
        if flow.attrib.get("sourceRef") not in gateways:
            _move_connector_name_to_documentation(flow)
    collaboration = _find_collaboration(root)
    if collaboration is not None:
        for flow in _message_flows(collaboration):
            _move_connector_name_to_documentation(flow)


def _move_connector_name_to_documentation(flow: ET.Element) -> None:
    name = flow.attrib.pop("name", "").strip()
    if not name:
        return
    documentation = ET.Element(_bpmn_tag("documentation"))
    documentation.text = name
    insert_at = 0
    for child in flow:
        if _namespace(child.tag) != BPMN_NS or _local_name(child.tag) != "documentation":
            break
        insert_at += 1
    flow.insert(insert_at, documentation)


def _avoid_node_label_collisions(
    plane: ET.Element,
    node_positions: dict[str, dict[str, float]],
    lane_shapes: list[dict[str, float | str]],
) -> None:
    """Move external labels away from connectors after all routes are known."""
    edges = [
        [(float(point.attrib["x"]), float(point.attrib["y"]))
         for point in edge.iter(f"{{{DI_NS}}}waypoint")]
        for edge in plane.iter(f"{{{BPMNDI_NS}}}BPMNEdge")
    ]
    labels: list[tuple[str, ET.Element, dict[str, float]]] = []
    for shape in plane.iter(f"{{{BPMNDI_NS}}}BPMNShape"):
        owner_id = shape.attrib.get("bpmnElement", "")
        if owner_id not in node_positions:
            continue
        bounds = shape.find(f"{{{BPMNDI_NS}}}BPMNLabel/{{{DC_NS}}}Bounds")
        if bounds is None:
            continue
        labels.append((owner_id, bounds, {key: float(bounds.attrib[key]) for key in ("x", "y", "width", "height")}))

    def overlaps(a: dict[str, float], b: dict[str, float], margin: float = 2) -> bool:
        return (a["x"] < b["x"] + b["width"] + margin
                and a["x"] + a["width"] + margin > b["x"]
                and a["y"] < b["y"] + b["height"] + margin
                and a["y"] + a["height"] + margin > b["y"])

    for owner_id, bounds_element, current in labels:
        owner = node_positions[owner_id]
        width, height = current["width"], current["height"]
        center_x = owner["x"] + owner["width"] / 2
        center_y = owner["y"] + owner["height"] / 2
        candidates = [
            current,
            {"x": center_x - width / 2, "y": owner["y"] + owner["height"] + 12,
             "width": width, "height": height},
            {"x": center_x - width / 2, "y": owner["y"] - height - 12,
             "width": width, "height": height},
            {"x": owner["x"] + owner["width"] + 14, "y": center_y - height / 2,
             "width": width, "height": height},
            {"x": owner["x"] - width - 14, "y": center_y - height / 2,
             "width": width, "height": height},
        ]
        containing_lane = next((lane for lane in lane_shapes
            if float(lane["x"]) <= center_x <= float(lane["x"]) + float(lane["width"])
            and float(lane["y"]) <= center_y <= float(lane["y"]) + float(lane["height"])), None)
        for candidate in candidates:
            if containing_lane and not (
                float(containing_lane["x"]) + 8 <= candidate["x"]
                and candidate["x"] + width <= float(containing_lane["x"]) + float(containing_lane["width"]) - 8
                and float(containing_lane["y"]) + 8 <= candidate["y"]
                and candidate["y"] + height <= float(containing_lane["y"]) + float(containing_lane["height"]) - 8
            ):
                continue
            if any(overlaps(candidate, box) for node_id, box in node_positions.items() if node_id != owner_id):
                continue
            if any(overlaps(candidate, other) for label_id, _, other in labels if label_id != owner_id):
                continue
            if any(_segment_crosses_box(start, end, candidate)
                   for points in edges for start, end in zip(points, points[1:])):
                continue
            current["x"], current["y"] = candidate["x"], candidate["y"]
            bounds_element.set("x", str(candidate["x"]))
            bounds_element.set("y", str(candidate["y"]))
            break

    edge_labels: list[tuple[ET.Element, dict[str, float], list[tuple[float, float]]]] = []
    for edge in plane.iter(f"{{{BPMNDI_NS}}}BPMNEdge"):
        bounds = edge.find(f"{{{BPMNDI_NS}}}BPMNLabel/{{{DC_NS}}}Bounds")
        if bounds is None:
            continue
        points = [(float(point.attrib["x"]), float(point.attrib["y"]))
                  for point in edge.iter(f"{{{DI_NS}}}waypoint")]
        edge_labels.append((bounds, {key: float(bounds.attrib[key])
                                    for key in ("x", "y", "width", "height")}, points))

    for bounds_element, current, points in edge_labels:
        verticals = [(a, b) for a, b in zip(points, points[1:]) if abs(a[0] - b[0]) < 2]
        if not verticals:
            continue
        longest = max(verticals, key=lambda segment: abs(segment[0][1] - segment[1][1]))
        line_x = longest[0][0]
        candidates = [current]
        for offset in (0, -45, 45):
            for x in (line_x - current["width"] - 14, line_x + 14):
                candidates.append({"x": x, "y": current["y"] + offset,
                                   "width": current["width"], "height": current["height"]})
        for candidate in candidates:
            if any(overlaps(candidate, box) for box in node_positions.values()):
                continue
            if any(overlaps(candidate, other) for _, _, other in labels):
                continue
            if any(overlaps(candidate, other) for other_bounds, other, _ in edge_labels
                   if other_bounds is not bounds_element):
                continue
            if any(_segment_crosses_box(start, end, candidate)
                   for route in edges for start, end in zip(route, route[1:])):
                continue
            current["x"], current["y"] = candidate["x"], candidate["y"]
            bounds_element.set("x", str(candidate["x"]))
            bounds_element.set("y", str(candidate["y"]))
            break


def _layout_flow_nodes(
    process: ET.Element,
    flow_nodes: list[ET.Element],
    config: BpmnLayoutConfig,
    planned_rows: list[list[str]] | None = None,
) -> dict[str, dict[str, float]]:
    lane_y_by_id, _local_rows, _lane_heights, row_pitch = _lane_geometry(
        process, flow_nodes, config, planned_rows
    )
    positions: dict[str, dict[str, float]] = {}
    cells = _lane_cells(process, flow_nodes, config, planned_rows)

    for element in flow_nodes:
        element_id = element.attrib["id"]
        element_type = _local_name(element.tag)
        width, height = _shape_size(element_type)
        cell = cells[element_id]
        row = cell["row"]
        column = cell["column"]
        lane_id = _effective_lane_id(process, element)
        if lane_id is None and lane_y_by_id:
            lane_id = next(iter(lane_y_by_id))
        lane_base_y = lane_y_by_id.get(lane_id or "", LAYOUT_TOP)
        x = LAYOUT_LEFT + LAYOUT_LANE_LABEL_WIDTH + 70 + column * config.column_gap
        y = lane_base_y + 52 + row * row_pitch + (80 - height) / 2
        positions[element_id] = {"x": x, "y": y, "width": width, "height": height}

    return positions


def _layout_lane_shapes(
    process: ET.Element,
    flow_nodes: list[ET.Element],
    config: BpmnLayoutConfig,
    planned_rows: list[list[str]] | None = None,
) -> list[dict[str, float | str]]:
    lanes = _lanes(process)
    if not lanes:
        return []

    lane_y_by_id, _local_rows, lane_heights, _row_pitch = _lane_geometry(
        process, flow_nodes, config, planned_rows
    )
    cells = _lane_cells(process, flow_nodes, config, planned_rows)
    last_column = max((cell["column"] for cell in cells.values()), default=0)
    lane_width = LAYOUT_LANE_LABEL_WIDTH + 70 + last_column * config.column_gap + 160
    lane_width = max(980, lane_width)
    return [
        {
            "id": lane.attrib["id"],
            "x": LAYOUT_LEFT,
            "y": lane_y_by_id[lane.attrib["id"]],
            "width": lane_width,
            "height": lane_heights[lane.attrib["id"]],
        }
        for lane in lanes
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


def _edge_waypoints(
    source: dict[str, float],
    target: dict[str, float],
    obstacles: Iterable[dict[str, float]] = (),
    source_flow_index: int = 0,
    source_is_boundary: bool = False,
) -> list[dict[str, float]]:
    start = {"x": source["x"] + source["width"], "y": source["y"] + source["height"] / 2}
    end = {"x": target["x"], "y": target["y"] + target["height"] / 2}

    blockers = [box for box in obstacles if box is not source and box is not target]
    if source_is_boundary and target["y"] > source["y"]:
        start = {"x": source["x"], "y": source["y"] + source["height"] / 2}
        end = {"x": target["x"], "y": target["y"] + target["height"] / 2}
        channel_x = min(source["x"], target["x"]) - 40
        direct = [start, {"x": channel_x, "y": start["y"]}, {"x": channel_x, "y": end["y"]}, end]
    elif (
        source_flow_index and source["width"] <= 60
        and target["x"] > source["x"] + source["width"] + 20
        and abs(target["y"] - source["y"]) > 100
    ):
        # The alternate branch leaves a gateway on its vertical side, then
        # reaches the activity along its lane. This keeps the sibling branch
        # free to run through the gap between lanes.
        downward = target["y"] > source["y"]
        start = {"x": source["x"] + source["width"] / 2,
                 "y": source["y"] + source["height"] if downward else source["y"]}
        end = {"x": target["x"], "y": target["y"] + target["height"] / 2}
        direct = [start, {"x": start["x"], "y": end["y"]}, end]
    elif (
        source["width"] > 60 and target["width"] <= 60
        and target["x"] > source["x"] + source["width"] + 20
        and abs(target["y"] - source["y"]) > 100
    ):
        downward = target["y"] > source["y"]
        start = {"x": source["x"] + source["width"] / 2,
                 "y": source["y"] + source["height"] if downward else source["y"]}
        end = {"x": target["x"] + target["width"] / 2,
               "y": target["y"] if downward else target["y"] + target["height"]}
        gap_y = (start["y"] + end["y"]) / 2
        direct = [start, {"x": start["x"], "y": gap_y},
                  {"x": end["x"], "y": gap_y}, end]
    elif target["y"] > source["y"] + source["height"] + 20:
        # A change of lane uses the gap beside the tasks. Distinct outgoing
        # flows take distinct ports and channels, so branches do not coincide.
        if source_flow_index == 0 and abs(target["x"] - source["x"]) < 12:
            preferred_x = source["x"] + source["width"] - 3
            candidate_xs = [preferred_x, source["x"] + 25, source["x"] + source["width"] / 2]
            clear_x = next((x for x in candidate_xs if not any(
                _segment_crosses_box((x, source["y"] + source["height"]), (x, target["y"]), box)
                for box in blockers
            )), preferred_x)
            start = {"x": clear_x, "y": source["y"] + source["height"]}
            end = {"x": clear_x, "y": target["y"]}
            direct = [start, end] if abs(start["x"] - end["x"]) < 2 else [
                start, {"x": start["x"], "y": (start["y"] + end["y"]) / 2},
                {"x": end["x"], "y": (start["y"] + end["y"]) / 2}, end,
            ]
        elif source_flow_index and target["x"] <= source["x"]:
            start = {"x": source["x"] + 8, "y": source["y"] + source["height"]}
            channel_x = min(target["x"] - 40, source["x"] - 40)
            end = {"x": target["x"], "y": target["y"] + target["height"] / 2}
            direct = [start, {"x": channel_x, "y": start["y"]}, {"x": channel_x, "y": end["y"]}, end]
        elif target["x"] > source["x"] + source["width"] + 20:
            channel_x = (source["x"] + source["width"] + target["x"]) / 2
            end = {"x": target["x"], "y": target["y"] + target["height"] / 2}
            direct = [start, {"x": channel_x, "y": start["y"]}, {"x": channel_x, "y": end["y"]}, end]
        else:
            channel_x = max(source["x"] + source["width"], target["x"] + target["width"]) + 40 + 40 * source_flow_index
            if source_flow_index:
                start = {"x": source["x"] + source["width"] - 8, "y": source["y"] + source["height"]}
            end = {"x": target["x"] + target["width"], "y": target["y"] + target["height"] / 2}
            direct = [start, {"x": channel_x, "y": start["y"]}, {"x": channel_x, "y": end["y"]}, end]
    elif target["x"] + target["width"] < source["x"] and abs(start["y"] - end["y"]) < 2:
        direct = [
            {"x": source["x"], "y": start["y"]},
            {"x": target["x"] + target["width"], "y": end["y"]},
        ]
    elif target["x"] > source["x"] and abs(start["y"] - end["y"]) < 2:
        direct = [start, end]
    elif target["x"] > source["x"]:
        mid_x = start["x"] + max(70, (end["x"] - start["x"]) / 2)
        direct = [start, {"x": mid_x, "y": start["y"]}, {"x": mid_x, "y": end["y"]}, end]
    else:
        route_y = max(source["y"] + source["height"], target["y"] + target["height"]) + 58
        direct = [
            start,
            {"x": start["x"] + 68, "y": start["y"]},
            {"x": start["x"] + 68, "y": route_y},
            {"x": end["x"] - 68, "y": route_y},
            {"x": end["x"] - 68, "y": end["y"]},
            end,
        ]

    crossing_boxes = [box for box in blockers if any(
        _segment_crosses_box((a["x"], a["y"]), (b["x"], b["y"]), box)
        for a, b in zip(direct, direct[1:])
    )]
    if not crossing_boxes:
        return direct

    # A skip edge (for example the default branch around an approval task)
    # must travel outside the occupied band, rather than through that task.
    candidates = []
    for above in (False, True):
        route_y = (
            min(box["y"] for box in [source, target, *crossing_boxes]) - 38
            if above else
            max(box["y"] + box["height"] for box in [source, target, *crossing_boxes]) + 38
        )
        start_y = source["y"] if above else source["y"] + source["height"]
        end_y = target["y"] if above else target["y"] + target["height"]
        sx = source["x"] + source["width"] / 2
        tx = target["x"] + target["width"] / 2
        points = [
            {"x": sx, "y": start_y},
            {"x": sx, "y": route_y},
            {"x": tx, "y": route_y},
            {"x": tx, "y": end_y},
        ]
        if not any(
            _segment_crosses_box((a["x"], a["y"]), (b["x"], b["y"]), box)
            for box in blockers for a, b in zip(points, points[1:])
        ):
            candidates.append((abs(start_y - route_y) + abs(sx - tx) + abs(end_y - route_y), points))
    return min(candidates, key=lambda candidate: candidate[0])[1] if candidates else direct


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


def _layout_grid(
    flow_nodes: list[ET.Element],
    config: BpmnLayoutConfig,
    planned_rows: list[list[str]] | None,
) -> dict[str, dict[str, int]]:
    element_ids = [element.attrib["id"] for element in flow_nodes if element.attrib.get("id")]
    known_ids = set(element_ids)
    rows: list[list[str]] = []
    used: set[str] = set()

    for planned_row in planned_rows or []:
        clean_row = []
        for element_id in planned_row:
            if element_id in known_ids and element_id not in used:
                clean_row.append(element_id)
                used.add(element_id)
        for index in range(0, len(clean_row), config.max_nodes_per_row):
            rows.append(clean_row[index : index + config.max_nodes_per_row])

    missing = [element_id for element_id in element_ids if element_id not in used]
    if planned_rows and missing:
        raise ValueError(
            "Il piano layout non copre tutti i flow node BPMN visibili: " + ", ".join(sorted(missing))
        )
    for index in range(0, len(missing), config.max_nodes_per_row):
        rows.append(missing[index : index + config.max_nodes_per_row])

    if not rows:
        rows = [element_ids]

    grid: dict[str, dict[str, int]] = {}
    for row_index, row in enumerate(rows):
        for column_index, element_id in enumerate(row):
            grid[element_id] = {
                "row": row_index,
                "column": column_index,
                "row_count": len(row),
            }
    return grid


def _layout_row_count(
    flow_nodes: list[ET.Element],
    config: BpmnLayoutConfig,
    planned_rows: list[list[str]] | None,
) -> int:
    grid = _layout_grid(flow_nodes, config, planned_rows)
    return max((cell["row"] + 1 for cell in grid.values()), default=1)


def _lane_cells(
    process: ET.Element,
    flow_nodes: list[ET.Element],
    config: BpmnLayoutConfig,
    planned_rows: list[list[str]] | None,
) -> dict[str, dict[str, int]]:
    """Give each lane its own ordered slots while retaining the plan's order."""
    grid = _layout_grid(flow_nodes, config, planned_rows)
    flow_order = _topological_node_order(process, flow_nodes)
    lanes = _lanes(process)
    first_lane = lanes[0].attrib["id"] if lanes else ""
    by_lane: dict[str, list[ET.Element]] = {}
    for element in flow_nodes:
        lane_id = _effective_lane_id(process, element) or first_lane
        by_lane.setdefault(lane_id, []).append(element)

    cells: dict[str, dict[str, int]] = {}
    capacity = config.max_nodes_per_row
    gateway_count = sum(_local_name(element.tag).endswith("Gateway") for element in flow_nodes)
    if len(by_lane) > 1 and (
        any(len(elements) > capacity for elements in by_lane.values()) or gateway_count >= 3
    ):
        # A multi-lane process needs one shared time axis. Independent wrapping
        # makes later cross-lane flows travel backwards through prior tasks.
        return {
            node_id: {"row": 0, "column": order}
            for node_id, order in flow_order.items()
        }
    for elements in by_lane.values():
        elements.sort(key=lambda element: flow_order[element.attrib["id"]])
        for offset in range(0, len(elements), capacity):
            row_elements = elements[offset : offset + capacity]
            first_column = grid[row_elements[0].attrib["id"]]["column"]
            if offset == 0:
                first_id = row_elements[0].attrib["id"]
                for flow in _sequence_flows(process):
                    if flow.attrib.get("targetRef") != first_id:
                        continue
                    predecessor_id = flow.attrib.get("sourceRef", "")
                    boundary = next((
                        node for node in process
                        if node.attrib.get("id") == predecessor_id
                        and _local_name(node.tag) == "boundaryEvent"
                    ), None)
                    if boundary is not None:
                        predecessor_id = boundary.attrib.get("attachedToRef", "")
                    if predecessor_id in cells:
                        first_column = cells[predecessor_id]["column"]
                        break
            start_column = min(first_column, capacity - len(row_elements))
            for index, element in enumerate(row_elements):
                row_index = offset // capacity
                column = capacity - 1 - index if row_index % 2 else start_column + index
                if row_index % 2 == 0 and _local_name(element.tag) == "endEvent" and index == len(row_elements) - 1:
                    column = capacity - 1
                cells[element.attrib["id"]] = {"row": row_index, "column": column}
    return cells


def _topological_node_order(
    process: ET.Element, flow_nodes: list[ET.Element]
) -> dict[str, int]:
    """Place every branch before the activity where it rejoins."""
    ids = [element.attrib["id"] for element in flow_nodes]
    original = {node_id: index for index, node_id in enumerate(ids)}
    successors: dict[str, list[str]] = {node_id: [] for node_id in ids}
    incoming = {node_id: 0 for node_id in ids}
    for flow in _sequence_flows(process):
        source_id = flow.attrib.get("sourceRef")
        target_id = flow.attrib.get("targetRef")
        if source_id in successors and target_id in incoming:
            successors[source_id].append(target_id)
            incoming[target_id] += 1

    available = [node_id for node_id in ids if incoming[node_id] == 0]
    result: list[str] = []
    while available:
        available.sort(key=original.__getitem__)
        node_id = available.pop(0)
        result.append(node_id)
        for target_id in successors[node_id]:
            incoming[target_id] -= 1
            if incoming[target_id] == 0:
                available.append(target_id)
    result.extend(node_id for node_id in ids if node_id not in result)
    return {node_id: index for index, node_id in enumerate(result)}


def _lane_geometry(
    process: ET.Element,
    flow_nodes: list[ET.Element],
    config: BpmnLayoutConfig,
    planned_rows: list[list[str]] | None = None,
) -> tuple[dict[str, float], dict[str, int], dict[str, float], int]:
    """Reserve only occupied rows in each lane, including room for data objects."""
    lanes = _lanes(process)
    if not lanes:
        return {}, {}, {}, config.row_gap

    cells = _lane_cells(process, flow_nodes, config, planned_rows)
    rows_by_lane: dict[str, set[int]] = {lane.attrib["id"]: set() for lane in lanes}
    local_row_by_node: dict[str, int] = {}
    for element in flow_nodes:
        node_id = element.attrib["id"]
        lane_id = _effective_lane_id(process, element) or lanes[0].attrib["id"]
        local_row_by_node[node_id] = cells[node_id]["row"]
        rows_by_lane[lane_id].add(cells[node_id]["row"])

    row_pitch = max(config.row_gap, config.lane_row_height + 30)
    lane_y_by_id: dict[str, float] = {}
    lane_heights: dict[str, float] = {}
    next_y = float(LAYOUT_TOP)
    for lane in lanes:
        lane_id = lane.attrib["id"]
        lane_y_by_id[lane_id] = next_y
        lane_heights[lane_id] = 30 + max(1, len(rows_by_lane[lane_id])) * row_pitch
        next_y += lane_heights[lane_id]
    return lane_y_by_id, local_row_by_node, lane_heights, row_pitch


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


def _effective_lane_id(process: ET.Element, element: ET.Element) -> str | None:
    """Keep an unassigned end event with the activity that completes the work."""
    element_id = element.attrib["id"]
    explicit = _lane_id_for_node(process, element_id)
    if explicit or _local_name(element.tag) != "endEvent":
        return explicit
    for flow in _sequence_flows(process):
        if flow.attrib.get("targetRef") == element_id:
            source_id = flow.attrib.get("sourceRef", "")
            source_lane = _lane_id_for_node(process, source_id)
            if source_lane:
                return source_lane
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


def _edge_shape_crossings(
    root: ET.Element, node_shapes: dict[str, dict[str, float]]
) -> list[tuple[str, str]]:
    """Find drawn connectors that pass through an unrelated flow node."""
    endpoints = {
        element.attrib["id"]: (element.attrib.get("sourceRef"), element.attrib.get("targetRef"))
        for element in root.iter()
        if _namespace(element.tag) == BPMN_NS
        and _local_name(element.tag) in {"sequenceFlow", "messageFlow", "association"}
        and element.attrib.get("id")
    }
    crossings: list[tuple[str, str]] = []
    for edge in root.iter():
        if _namespace(edge.tag) != BPMNDI_NS or _local_name(edge.tag) != "BPMNEdge":
            continue
        edge_id = edge.attrib.get("bpmnElement")
        if not edge_id or edge_id not in endpoints:
            continue
        points = []
        for waypoint in edge:
            if _namespace(waypoint.tag) != DI_NS or _local_name(waypoint.tag) != "waypoint":
                continue
            try:
                points.append((float(waypoint.attrib["x"]), float(waypoint.attrib["y"])))
            except (KeyError, ValueError):
                continue
        source_id, target_id = endpoints[edge_id]
        for node_id, bounds in node_shapes.items():
            if node_id in {source_id, target_id}:
                continue
            if any(_segment_crosses_box(start, end, bounds) for start, end in zip(points, points[1:])):
                crossings.append((edge_id, node_id))
    return crossings


def _edge_edge_crossings(root: ET.Element) -> list[tuple[str, str]]:
    """Report interior intersections and shared stretches between connectors."""
    edges: list[tuple[str, list[tuple[float, float]]]] = []
    for edge in root.iter(f"{{{BPMNDI_NS}}}BPMNEdge"):
        points = [
            (float(point.attrib["x"]), float(point.attrib["y"]))
            for point in edge.iter(f"{{{DI_NS}}}waypoint")
        ]
        if len(points) > 1:
            edges.append((edge.attrib.get("bpmnElement", ""), points))

    crossings = []
    for index, (left_id, left_points) in enumerate(edges):
        for right_id, right_points in edges[index + 1:]:
            if any(
                _segments_overlap_interior(a, b, c, d)
                for a, b in zip(left_points, left_points[1:])
                for c, d in zip(right_points, right_points[1:])
            ):
                crossings.append((left_id, right_id))
    return crossings


def _segments_overlap_interior(
    a: tuple[float, float], b: tuple[float, float],
    c: tuple[float, float], d: tuple[float, float],
) -> bool:
    epsilon = 2.0
    ah = abs(a[1] - b[1]) < epsilon
    bh = abs(c[1] - d[1]) < epsilon
    av = abs(a[0] - b[0]) < epsilon
    bv = abs(c[0] - d[0]) < epsilon
    if ah and bh and abs(a[1] - c[1]) < epsilon:
        return min(max(a[0], b[0]), max(c[0], d[0])) - max(min(a[0], b[0]), min(c[0], d[0])) > epsilon
    if av and bv and abs(a[0] - c[0]) < epsilon:
        return min(max(a[1], b[1]), max(c[1], d[1])) - max(min(a[1], b[1]), min(c[1], d[1])) > epsilon
    if ah and bv:
        return (min(a[0], b[0]) + epsilon < c[0] < max(a[0], b[0]) - epsilon
                and min(c[1], d[1]) + epsilon < a[1] < max(c[1], d[1]) - epsilon)
    if av and bh:
        return _segments_overlap_interior(c, d, a, b)
    return False


def _segment_crosses_box(
    start: tuple[float, float], end: tuple[float, float], bounds: dict[str, float]
) -> bool:
    """Clip a segment against the interior of a shape, ignoring border touches."""
    inset = 2.0
    left, right = bounds["x"] + inset, bounds["x"] + bounds["width"] - inset
    top, bottom = bounds["y"] + inset, bounds["y"] + bounds["height"] - inset
    dx, dy = end[0] - start[0], end[1] - start[1]
    low, high = 0.0, 1.0
    for p, q in ((-dx, start[0] - left), (dx, right - start[0]),
                 (-dy, start[1] - top), (dy, bottom - start[1])):
        if p == 0:
            if q <= 0:
                return False
            continue
        t = q / p
        if p < 0:
            low = max(low, t)
        else:
            high = min(high, t)
        if low >= high:
            return False
    return True


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
    if lane_shapes:
        # A lane is a subdivision of its participant, not an inset box.
        # Its first and last edges must coincide with the pool border; the
        # remaining 30 px on the left are the participant's title strip.
        pool_left = min(float(lane["x"]) for lane in lane_shapes) - 30
        pool_right = max(float(lane["x"]) + float(lane["width"]) for lane in lane_shapes)
        primary_top = min(float(lane["y"]) for lane in lane_shapes)
        primary_bottom = max(float(lane["y"]) + float(lane["height"]) for lane in lane_shapes)
        pool_width = pool_right - pool_left
        primary_height = primary_bottom - primary_top
    else:
        pool_left = min_x - 30
        pool_width = (max_x - pool_left) + 40
        primary_top = min_y - 30
        primary_height = max(max_y - primary_top + 30, 160.0)

    positions: dict[str, dict[str, float]] = {}
    external_count = 0
    for participant in participants:
        participant_id = participant.attrib.get("id")
        if not participant_id:
            continue
        if participant.attrib.get("processRef") == process_id:
            box = {"x": pool_left, "y": primary_top, "width": pool_width, "height": primary_height}
        else:
            # In the OMG collaboration examples, each participant owns a
            # separate horizontal pool. The first black box sits above the
            # modeled pool; additional participants stack below it.
            external_y = (
                primary_top - 150 if external_count == 0
                else primary_top + primary_height + 50 + (external_count - 1) * 150
            )
            box = {
                "x": pool_left,
                "y": external_y,
                "width": pool_width,
                "height": 100.0,
            }
            external_count += 1
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
        source_ref = message_flow.attrib.get("sourceRef")
        target_ref = message_flow.attrib.get("targetRef")
        source = endpoint_positions.get(source_ref) if source_ref else None
        target = endpoint_positions.get(target_ref) if target_ref else None
        if not flow_id or source is None or target is None:
            continue

        start_x = source["x"] + source["width"] / 2
        end_x = target["x"] + target["width"] / 2
        # A message between a full-width participant and an activity docks
        # opposite that activity. Keep the connection vertical in the gap.
        if source["width"] > 500 and target["width"] <= 110:
            start_x = end_x
        elif target["width"] > 500 and source["width"] <= 110:
            end_x = start_x
        if source["y"] <= target["y"]:
            start_y, end_y = source["y"] + source["height"], target["y"]
        else:
            start_y, end_y = source["y"], target["y"] + target["height"]
        points = [(start_x, start_y), (end_x, end_y)]

        edge = ET.SubElement(
            plane,
            _bpmndi_tag("BPMNEdge"),
            {"id": f"{flow_id}_di", "bpmnElement": flow_id},
        )
        for x, y in points:
            ET.SubElement(edge, _di_tag("waypoint"), {"x": str(x), "y": str(y)})


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
