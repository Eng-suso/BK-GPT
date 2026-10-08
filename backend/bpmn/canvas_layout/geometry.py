"""Graph ranks determine X; semantic ownership determines lane bands and Y."""
from collections import defaultdict
from dataclasses import dataclass

from .policy import BPMN, ARTIFACT_TYPES, FLOW_TYPES, ENTERPRISE_POLICY, local_name, tag
from .ranks import rank_process


@dataclass(frozen=True)
class Box:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self):
        return self.x + self.width

    @property
    def bottom(self):
        return self.y + self.height

    @property
    def center(self):
        return (self.x + self.width / 2, self.y + self.height / 2)

    def expanded(self, margin):
        return Box(self.x - margin, self.y - margin, self.width + margin * 2, self.height + margin * 2)


def semantic_connections(root):
    parents = {child: parent for parent in root.iter() for child in parent}
    nodes = {e.get("id") for e in root.iter() if local_name(e) in FLOW_TYPES and e.tag.startswith("{" + BPMN + "}")}
    result = []
    for e in root.iter():
        kind = local_name(e)
        if kind in {"sequenceFlow", "association", "messageFlow"} and e.get("id"):
            result.append((e, e.get("sourceRef"), e.get("targetRef")))
        elif kind in {"dataInputAssociation", "dataOutputAssociation"} and e.get("id"):
            source = e.findtext(tag("sourceRef"))
            target = e.findtext(tag("targetRef"))
            owner = parents.get(e)
            while owner is not None and owner.get("id") not in nodes:
                owner = parents.get(owner)
            if owner is not None:
                if kind == "dataInputAssociation":
                    target = owner.get("id")
                else:
                    source = owner.get("id")
            result.append((e, source, target))
    return sorted(result, key=lambda item: (local_name(item[0]) != "sequenceFlow", item[0].get("id")))


def layout_process(process, top: float, connections):
    p = ENTERPRISE_POLICY
    initial_top = top
    nodes = {e.get("id"): e for e in process if local_name(e) in FLOW_TYPES and e.tag.startswith("{" + BPMN + "}")}
    ranks, feedback, parents = rank_process(process, nodes)
    ordinary = {node_id: node for node_id, node in nodes.items() if local_name(node) != "boundaryEvent"}
    # All end events sit at the terminal rank, including early termination paths.
    terminal = max((ranks[i] for i in ordinary if local_name(ordinary[i]) != "endEvent"), default=0) + 1
    for node_id in ordinary:
        if local_name(ordinary[node_id]) == "endEvent":
            ranks[node_id] = terminal
    lanes = list(process.iter(tag("lane")))
    owner = {ref.text: lane.get("id") for lane in lanes for ref in lane.findall(tag("flowNodeRef"))}
    # Event/gateway placement may inherit a neighboring visual band. This does
    # not assign ownership or create flowNodeRefs in the semantic model.
    for node_id in sorted(nodes, key=lambda i: (ranks[i], i)):
        if node_id in owner or not (local_name(nodes[node_id]).endswith("Event") or local_name(nodes[node_id]).endswith("Gateway")):
            continue
        host = nodes[node_id].get("attachedToRef")
        adjacent = sorted(parents[node_id], key=lambda i: (-ranks[i], i))
        adjacent += sorted(target for e, source, target in connections if source == node_id and target in nodes)
        candidates = ([host] if host else []) + adjacent
        choice = next((owner[i] for i in candidates if i in owner), None)
        if choice:
            owner[node_id] = choice
    lane_order = sorted(lanes, key=lambda lane: (
        min((ranks.get(ref.text, terminal + 1) for ref in lane.findall(tag("flowNodeRef"))), default=terminal + 1),
        min((e.get("id") for e, _, target in connections if target in {ref.text for ref in lane.findall(tag("flowNodeRef"))} and local_name(e) == "sequenceFlow"), default=""),
        lane.get("id"),
    ))
    bands = [lane.get("id") for lane in lane_order]
    if any(node_id not in owner for node_id in ordinary) or not bands:
        bands.append(None)  # Unassigned work stays unassigned; never invent a role.
    sizes = {node_id: _size(node) for node_id, node in ordinary.items()}
    column_widths = defaultdict(lambda: p.event_size)
    for node_id in ordinary:
        column_widths[ranks[node_id]] = max(column_widths[ranks[node_id]], sizes[node_id][0], 160 if ordinary[node_id].get("name") and (local_name(ordinary[node_id]).endswith("Event") or local_name(ordinary[node_id]).endswith("Gateway")) else 0)
    centers, x = {}, p.origin_x + p.pool_label_width + p.lane_label_width + p.padding
    for rank in sorted(column_widths):
        centers[rank] = x + column_widths[rank] / 2
        x += column_widths[rank] + p.column_gap
    right = x - p.column_gap + p.padding if centers else x + p.task_width
    boxes, lane_boxes = {}, {}
    artifacts = {e.get("id"): e for e in process if local_name(e) in ARTIFACT_TYPES and e.get("id")}
    artifact_owner = {}
    for artifact_id in artifacts:
        neighbors = {other for _, source, target in connections for other in ([target] if source == artifact_id else [source] if target == artifact_id else []) if other in ordinary}
        neighbor = min(neighbors, key=lambda i: (ranks[i], i)) if neighbors else None
        artifact_owner[artifact_id] = (owner.get(neighbor), ranks.get(neighbor, 0))
    if any(band is None for band, _ in artifact_owner.values()) and None not in bands:
        bands.append(None)
    for band in bands:
        grouped = defaultdict(list)
        for node_id in ordinary:
            if owner.get(node_id) == band:
                grouped[ranks[node_id]].append(node_id)
        rows = max((len(group) for group in grouped.values()), default=1)
        content_height = max((sizes[i][1] + (52 if nodes[i].get("name") and (local_name(nodes[i]).endswith("Event") or local_name(nodes[i]).endswith("Gateway")) else 0) for group in grouped.values() for i in group), default=p.task_height)
        main_height = (rows - 1) * p.row_gap + content_height + p.padding * 2
        if any(e.get("id") in feedback and owner.get(source) == band for e, source, _ in connections):
            main_height += 80  # An interior return channel and readable labels.
        doc_groups = defaultdict(list)
        for artifact_id, (doc_band, rank) in artifact_owner.items():
            if doc_band == band:
                doc_groups[rank].append(artifact_id)
        doc_rows = max((len(group) for group in doc_groups.values()), default=0)
        boundary_count = max((sum(node.get("attachedToRef") == host for node in nodes.values()) for host in ordinary if owner.get(host) == band), default=0)
        boundary_space = 80 + boundary_count * 52 if boundary_count else 0
        band_height = main_height + boundary_space + (p.padding + doc_rows * 120 if doc_rows else 0)
        if band is not None:
            lane_boxes[band] = Box(p.origin_x + p.pool_label_width, top, right - p.origin_x - p.pool_label_width, band_height)
        for rank, group in sorted(grouped.items()):
            # The predecessor order is stable and keeps paired branches on the
            # same vertical tracks; single split/join gateways stay centered.
            group.sort(key=lambda i: (tuple(sorted(parents[i])), i))
            for row, node_id in enumerate(group):
                width, height = sizes[node_id]
                cy = top + main_height / 2 + (row - (len(group) - 1) / 2) * p.row_gap
                boxes[node_id] = Box(centers[rank] - width / 2, cy - height / 2, width, height)
        for rank, group in sorted(doc_groups.items()):
            for index, artifact_id in enumerate(sorted(group)):
                row = index
                cx = centers.get(rank, p.origin_x + p.padding + 100)
                width, height = (160, 60) if local_name(artifacts[artifact_id]) == "textAnnotation" else (64, 54)
                boxes[artifact_id] = Box(cx - width / 2, top + main_height + boundary_space + p.padding + row * 120, width, height)
        top += band_height
    for node_id, node in nodes.items():
        if local_name(node) != "boundaryEvent":
            continue
        host = boxes.get(node.get("attachedToRef"))
        if host is None:
            raise ValueError(f"Evento boundary {node_id} senza posizione dell'attività ospite.")
        siblings = sorted(i for i, e in nodes.items() if e.get("attachedToRef") == node.get("attachedToRef"))
        index = siblings.index(node_id)
        cx = host.center[0] + (index - (len(siblings) - 1) / 2) * 48
        boxes[node_id] = Box(cx - 18, host.bottom - 18, 36, 36)
    return boxes, lane_boxes, ranks, feedback, Box(p.origin_x, initial_top, right - p.origin_x, top - initial_top), top


def _size(node):
    p = ENTERPRISE_POLICY
    kind = local_name(node)
    if kind.endswith("Event"):
        return p.event_size, p.event_size
    if kind.endswith("Gateway"):
        return p.gateway_size, p.gateway_size
    name_length = len(node.get("name", ""))
    return (p.task_width if name_length <= 48 else 200, p.task_height if name_length <= 80 else 100)
