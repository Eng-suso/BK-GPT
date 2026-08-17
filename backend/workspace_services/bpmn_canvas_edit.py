from __future__ import annotations

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
    root = _parse_bpmn_xml(xml)
    element = _find_editable_element(root, element_id)
    element_type = _local_name(element.tag)

    removed_flows = []
    if element_type != "sequenceFlow":
        for flow in list(_sequence_flows(root)):
            if flow.attrib.get("sourceRef") == element_id or flow.attrib.get("targetRef") == element_id:
                flow_id = flow.attrib.get("id", "")
                removed_flows.append(flow_id)
                if flow_id:
                    _remove_flow_references(root, flow_id)
                _remove_element(root, flow)

    if element_type == "sequenceFlow":
        _remove_flow_references(root, element_id)
    _remove_element(root, element)

    updated_xml = layout_bpmn_di(_xml_to_string(root))
    return updated_xml, {
        "action": "delete",
        "id": element_id,
        "type": element_type,
        "removed_connected_flows": [flow_id for flow_id in removed_flows if flow_id],
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


def layout_bpmn_di(xml: str) -> str:
    root = _parse_bpmn_xml(xml)
    definitions_id = root.attrib.get("id", "Definitions")
    process = _find_process(root)

    for child in list(root):
        if _namespace(child.tag) == BPMNDI_NS and _local_name(child.tag) == "BPMNDiagram":
            root.remove(child)

    diagram = ET.SubElement(root, _bpmndi_tag("BPMNDiagram"), {"id": f"{definitions_id}_Diagram"})
    plane = ET.SubElement(
        diagram,
        _bpmndi_tag("BPMNPlane"),
        {
            "id": f"{process.attrib.get('id', 'Process')}_Plane",
            "bpmnElement": process.attrib.get("id", "Process"),
        },
    )

    node_positions = {}
    x = 160
    y = 120
    for element in process:
        element_type = _local_name(element.tag)
        element_id = element.attrib.get("id")
        if not element_id or element_type not in FLOW_NODE_TYPES:
            continue

        width, height = _shape_size(element_type)
        node_positions[element_id] = {"x": x, "y": y, "width": width, "height": height}
        shape = ET.SubElement(
            plane,
            _bpmndi_tag("BPMNShape"),
            {"id": f"{element_id}_di", "bpmnElement": element_id},
        )
        ET.SubElement(
            shape,
            _dc_tag("Bounds"),
            {
                "x": str(x),
                "y": str(y),
                "width": str(width),
                "height": str(height),
            },
        )
        x += 180

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
            {
                "x": str(source["x"] + source["width"]),
                "y": str(source["y"] + source["height"] // 2),
            },
        )
        ET.SubElement(
            edge,
            _di_tag("waypoint"),
            {
                "x": str(target["x"]),
                "y": str(target["y"] + target["height"] // 2),
            },
        )

    return _xml_to_string(root)


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


def _remove_element(root: ET.Element, target: ET.Element) -> None:
    for parent in root.iter():
        for child in list(parent):
            if child is target:
                parent.remove(child)
                return

    raise ValueError("Elemento BPMN non rimosso.")


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
