"""Mandatory semantic normalization → layout → visual lint → BPMN DI."""
import xml.etree.ElementTree as ET

from .geometry import Box, layout_process, semantic_connections
from .labels import branch_label, node_label
from .lint import lint_visual_model
from .normalizer import normalize_semantics
from .policy import BPMN, BPMNDI, DC, DI, ENTERPRISE_POLICY, CanvasLayoutPolicy, local_name, tag
from .ports import assign_ports
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
            containers[participant.get("id")] = Box(p.origin_x, top, width, 64)
            top += 64 + p.padding * 2
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
    pools = {key: box for key, box in containers.items() if local_name(elements[key]) == "participant"}
    routable = [(c.get("id"), local_name(c), source, target) for c, source, target in connections
                if {source, target} <= boxes.keys() | pools.keys() and local_name(elements[source]) != "boundaryEvent"]
    ports = assign_ports(
        [(flow_id, source, target) for flow_id, kind, source, target in routable if kind == "sequenceFlow"],
        boxes,
        attachments=[(flow_id, source, target) for flow_id, kind, source, target in routable if kind != "sequenceFlow"],
        reserved={e.get("attachedToRef"): {"bottom"} for e in elements.values() if local_name(e) == "boundaryEvent"},
        pools=pools,
    )
    docked, turns = set(), set()
    for connection, source, target in connections:
        if connection.get("id") not in ports:
            continue
        for node, other, port in ((source, target, ports[connection.get("id")][0]), (target, source, ports[connection.get("id")][1])):
            docked.add((node, port.side))
            if node in boxes and other in boxes:
                (nx, ny), (ox, oy) = boxes[node].center, boxes[other].center
                if ox != nx and oy != ny:
                    turns.add((node, ("right" if ox > nx else "left", "bottom" if oy > ny else "top")))
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
                pool = next((c for key, c in containers.items() if local_name(elements[key]) == "participant"
                             and c.x <= box.x and c.y <= box.y and c.right >= box.right and c.bottom >= box.bottom), None)
                lanes_boxes = [c for key, c in containers.items() if local_name(elements[key]) == "lane"]
                sides = {side for node, side in docked if node == element_id}
                corners = {corner for node, corner in turns if node == element_id}
                label = node_label(box, elements[element_id].get("name"), sides, boxes, labels, pool, lanes_boxes, corners)
            labels[element_id] = label
            _bounds(ET.SubElement(shape, f"{{{BPMNDI}}}BPMNLabel"), label)
    # Feedback routes come last; they may use outer channels without changing
    # the forward happy-path rank assignment.
    previous = []
    for connection, source, target in sorted(connections, key=lambda item: (item[0].get("id") in feedback, local_name(item[0]) != "sequenceFlow", item[0].get("id"))):
        positions = {**boxes, **pools}
        if source not in positions or target not in positions:
            raise ValueError(f"Collegamento senza estremi visibili: {connection.get('id')}.")
        obstacle_boxes = dict(boxes)
        obstacle_boxes[source], obstacle_boxes[target] = positions[source], positions[target]
        points = orthogonal_route(source, target, obstacle_boxes, labels, previous,
                                  downward=local_name(elements[source]) == "boundaryEvent",
                                  ports=ports.get(connection.get("id")))
        edge = ET.SubElement(plane, f"{{{BPMNDI}}}BPMNEdge", {"id": allocate(f"{connection.get('id')}_di"), "bpmnElement": connection.get("id")})
        for x, y in points:
            ET.SubElement(edge, f"{{{DI}}}waypoint", {"x": _number(x), "y": _number(y)})
        if connection.get("name") and local_name(connection) == "sequenceFlow":
            container = next((box for key, box in containers.items() if local_name(elements[key]) == "participant" and box.x <= boxes[source].x and box.y <= boxes[source].y and box.right >= boxes[source].right and box.bottom >= boxes[source].bottom), None)
            lane_boundaries = [box for key, box in containers.items() if local_name(elements[key]) == "lane"]
            label = branch_label(points, connection.get("name"), boxes, labels, previous, container, lane_boundaries)
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
