"""Mandatory semantic normalization → layout → visual lint → BPMN DI."""
import xml.etree.ElementTree as ET

from .geometry import Box, layout_process, semantic_connections
from .labels import branch_label
from .lint import lint_visual_model
from .normalizer import normalize_semantics
from .policy import BPMN, BPMNDI, DC, DI, ENTERPRISE_POLICY, CanvasLayoutPolicy, local_name, tag
from .router import orthogonal_route

__all__ = ["apply_enterprise_layout", "CanvasLayoutPolicy", "ENTERPRISE_POLICY", "lint_visual_model"]

for prefix, uri in (("bpmn", BPMN), ("bpmndi", BPMNDI), ("dc", DC), ("di", DI)):
    ET.register_namespace(prefix, uri)


def apply_enterprise_layout(process_model, *, process_name: str | None = None) -> str:
    """Agent geometry is discarded, including DI in raw proposed XML.

    Semantic IDs, owners, conditions, documentation and provenance survive.
    No LLM tool receives policy, rank, position or routing parameters.
    """
    if not isinstance(process_model, str):
        from backend.bpmn.serializer import semantic_model_to_bpmn_xml
        process_model = semantic_model_to_bpmn_xml(process_model, include_di=False)
    root = normalize_semantics(process_model, process_name)
    connections = semantic_connections(root)
    p = ENTERPRISE_POLICY
    boxes, containers, ranks, feedback = {}, {}, {}, set()
    top = p.origin_y
    participants = list(root.iter(tag("participant")))
    for process in sorted(root.findall(tag("process")), key=lambda e: e.get("id")):
        placed, lanes, process_ranks, loops, boundary, bottom = layout_process(process, top, connections)
        boxes.update(placed)
        containers.update(lanes)
        ranks.update(process_ranks)
        feedback.update(loops)
        participant = next((e for e in participants if e.get("processRef") == process.get("id")), None)
        if participant is not None:
            containers[participant.get("id")] = boundary
        top = bottom + p.padding * 2
    width = max((box.right for box in [*boxes.values(), *containers.values()]), default=500) - p.origin_x
    for participant in sorted(participants, key=lambda e: e.get("id")):
        if participant.get("id") not in containers:
            containers[participant.get("id")] = Box(p.origin_x, top, width, 100)
            top += 100 + p.padding * 2
    collaboration = root.find(tag("collaboration"))
    plane_ref = collaboration.get("id") if collaboration is not None else root.find(tag("process")).get("id")
    taken = {e.get("id") for e in root.iter() if e.get("id")}

    def allocate(seed):
        candidate, number = seed, 1
        while candidate in taken:
            candidate, number = f"{seed}_{number}", number + 1
        taken.add(candidate)
        return candidate

    diagram = ET.SubElement(root, f"{{{BPMNDI}}}BPMNDiagram", {"id": allocate("DeliR_Diagram")})
    plane = ET.SubElement(diagram, f"{{{BPMNDI}}}BPMNPlane", {"id": allocate("DeliR_Plane"), "bpmnElement": plane_ref})
    elements = {e.get("id"): e for e in root.iter() if e.get("id")}
    labels = {}
    for element_id, box in sorted({**containers, **boxes}.items(), key=lambda item: (item[0] in boxes, ranks.get(item[0], -1), item[0])):
        kind = local_name(elements[element_id])
        attrs = {"id": allocate(f"{element_id}_di"), "bpmnElement": element_id}
        if kind in {"participant", "lane"}:
            attrs["isHorizontal"] = "true"
        if kind == "subProcess":
            attrs["isExpanded"] = "false"
        shape = ET.SubElement(plane, f"{{{BPMNDI}}}BPMNShape", attrs)
        _bounds(shape, box)
        if elements[element_id].get("name") and (kind.endswith("Event") or kind.endswith("Gateway") or kind in {"dataObjectReference", "dataStoreReference"}):
            if kind == "boundaryEvent":
                host_id = elements[element_id].get("attachedToRef")
                siblings = sorted(i for i, e in elements.items() if e.get("attachedToRef") == host_id)
                label = Box(boxes[host_id].center[0] - 70, boxes[host_id].bottom + 58 + siblings.index(element_id) * 52, 140, 44)
            else:
                label = Box(box.center[0] - 70, box.bottom + 8, 140, 44)
            labels[element_id] = label
            _bounds(ET.SubElement(shape, f"{{{BPMNDI}}}BPMNLabel"), label)
    # Feedback routes come last; they may use outer channels without changing
    # the forward happy-path rank assignment.
    previous = []
    for connection, source, target in sorted(connections, key=lambda item: (item[0].get("id") in feedback, local_name(item[0]) != "sequenceFlow", item[0].get("id"))):
        positions = {**boxes, **{key: box for key, box in containers.items() if local_name(elements[key]) == "participant"}}
        if source not in positions or target not in positions:
            if local_name(connection) == "sequenceFlow":
                raise ValueError(f"Collegamento senza nodi visibili: {connection.get('id')}.")
            continue
        obstacle_boxes = dict(boxes)
        obstacle_boxes[source], obstacle_boxes[target] = positions[source], positions[target]
        points = orthogonal_route(source, target, obstacle_boxes, labels, previous,
                                  downward=local_name(elements[source]) == "boundaryEvent")
        edge = ET.SubElement(plane, f"{{{BPMNDI}}}BPMNEdge", {"id": allocate(f"{connection.get('id')}_di"), "bpmnElement": connection.get("id")})
        for x, y in points:
            ET.SubElement(edge, f"{{{DI}}}waypoint", {"x": _number(x), "y": _number(y)})
        if connection.get("name") and local_name(connection) == "sequenceFlow":
            label = branch_label(points, connection.get("name"), boxes, labels, previous)
            labels[connection.get("id")] = label
            _bounds(ET.SubElement(edge, f"{{{BPMNDI}}}BPMNLabel"), label)
        previous.append(points)
    report = lint_visual_model(root)
    if not report["valid"]:
        raise ValueError("CanvasLayoutPolicy: " + "; ".join(report["issues"]))
    return ET.tostring(root, encoding="unicode")


def _bounds(parent, box):
    ET.SubElement(parent, f"{{{DC}}}Bounds", {key: _number(value) for key, value in zip(("x", "y", "width", "height"), (box.x, box.y, box.width, box.height), strict=True)})


def _number(value):
    return format(value, ".6f").rstrip("0").rstrip(".")
