"""Stable graph ranks; source XML order and incoming DI are irrelevant."""
from collections import deque

from .policy import local_name, tag


def rank_process(process, nodes: dict) -> tuple[dict[str, int], set[str], dict[str, list[str]], set[str]]:
    adjacency = {node_id: [] for node_id in nodes}
    flows = sorted(process.findall(tag("sequenceFlow")), key=lambda e: e.get("id", ""))
    for flow in flows:
        adjacency[flow.get("sourceRef")].append((flow.get("targetRef"), flow.get("id")))
    for node_id in adjacency:
        default = nodes[node_id].get("default")
        adjacency[node_id].sort(key=lambda pair: (pair[1] != default, pair[1], pair[0]))
    color, feedback = {}, set()

    ordered = sorted(nodes, key=lambda node_id: (local_name(nodes[node_id]) != "startEvent", node_id))
    for node_id in ordered:
        if not color.get(node_id):
            color[node_id] = 1
            stack = [(node_id, iter(adjacency[node_id]))]
            while stack:
                current, children = stack[-1]
                child = next(children, None)
                if child is None:
                    color[current] = 2
                    stack.pop()
                    continue
                target, flow_id = child
                if color.get(target) == 1:
                    feedback.add(flow_id)
                elif not color.get(target):
                    color[target] = 1
                    stack.append((target, iter(adjacency[target])))
    parents = {node_id: [] for node_id in nodes}
    forward = {node_id: [] for node_id in nodes}
    for source in adjacency:
        for target, flow_id in adjacency[source]:
            if flow_id not in feedback:
                parents[target].append(source)
                forward[source].append(target)
    for node_id, node in nodes.items():
        host = node.get("attachedToRef") if local_name(node) == "boundaryEvent" else None
        if host in nodes and host not in parents[node_id]:
            parents[node_id].append(host)
            forward[host].append(node_id)
    lane_set = process.find(tag("laneSet"))
    lane_index = {ref.text: index for index, lane in enumerate(lane_set.iter(tag("lane")) if lane_set is not None else [])
                  for ref in lane.findall(tag("flowNodeRef"))}
    documented = _with_documents(process, nodes)

    def step(source: str, target: str) -> int:
        if nodes[target].get("attachedToRef") == source:
            return 0
        # A decision handing over to a lane below drops straight down: the
        # branch takes the decision's column, so the handover is one vertical.
        # Not onto a node with a document underneath, which the drop would cross.
        if (local_name(nodes[source]).endswith("Gateway") and len(parents[target]) == 1
                and lane_index.get(target, -1) > lane_index.get(source, -1) >= 0 and target not in documented):
            return 0
        return 1

    degree = {node_id: len(parents[node_id]) for node_id in nodes}
    ready = deque(sorted(node_id for node_id in nodes if degree[node_id] == 0))
    ranks = {node_id: 0 for node_id in nodes}
    while ready:
        source = ready.popleft()
        for target in forward[source]:
            ranks[target] = max(ranks[target], ranks[source] + step(source, target))
            degree[target] -= 1
            if degree[target] == 0:
                ready.append(target)
    rework = _compact_rework_loops(nodes, forward, parents, feedback, flows, ranks, lane_index)
    connected = {ref for flow in flows for ref in (flow.get("sourceRef"), flow.get("targetRef"))}
    owners = {ref.text: lane.get("id", "") for lane in lane_set.iter(tag("lane")) for ref in lane.findall(tag("flowNodeRef"))} if lane_set is not None else {}
    isolated = sorted((i for i in nodes if i not in connected and local_name(nodes[i]) not in {"boundaryEvent", "startEvent", "endEvent"}), key=lambda i: (owners.get(i, ""), i))
    for index, node_id in enumerate(isolated):
        ranks[node_id] = index
    # Boundary events leave their host rather than participating in the happy path.
    for node_id, node in nodes.items():
        if local_name(node) == "boundaryEvent":
            ranks[node_id] = ranks.get(node.get("attachedToRef"), ranks[node_id])
    # A compensation activity stands under the activity it undoes: its boundary
    # event points to it through an association (OMG BPMN 2.0, 10.6).
    for association in process.findall(tag("association")):
        source, target = nodes.get(association.get("sourceRef")), association.get("targetRef")
        if source is not None and local_name(source) == "boundaryEvent" and target in nodes and nodes[target].get("isForCompensation") == "true":
            ranks[target] = ranks[source.get("id")]
    return ranks, feedback, parents, rework


def _compact_rework_loops(nodes, forward, parents, feedback, flows, ranks, lane_index) -> set[str]:
    """Keep a rework loop next to the decision that opens it; return its nodes.

    A node that cannot reach an end without going round the loop again (its
    only way on is a return flow) is rework: by longest path it would sit one
    column further right at every step, and the return would cross the whole
    diagram back to the activity it repeats. Rework takes its parent's column
    instead and stacks beside it (`assign_tracks` puts it on the side of the
    lane it heads for), so the loop stays local and the main path keeps
    running left to right. Only a loop that hands the work to another lane is
    compacted: one that stays in its lane is the process's own cycle (OMG
    "Issue list") and keeps running along the main line.
    """
    loop_sources = {flow.get("sourceRef") for flow in flows if flow.get("id") in feedback}
    if not loop_sources:
        return set()
    ends = {node_id for node_id, node in nodes.items() if local_name(node) == "endEvent"}
    reaches_end: dict[str, bool] = {}

    def to_end(node_id: str) -> bool:
        if node_id not in reaches_end:
            reaches_end[node_id] = False  # a cycle never reaches an end by itself
            reaches_end[node_id] = node_id in ends or any(to_end(child) for child in forward[node_id])
        return reaches_end[node_id]

    rework = {
        node_id for node_id, node in nodes.items()
        if local_name(node) != "boundaryEvent" and parents[node_id] and not to_end(node_id)
        and (node_id in loop_sources or any(child in loop_sources for child in _closure(node_id, forward)))
    }
    for entry in [i for i in rework if not any(parent in rework for parent in parents[i])]:
        chain = {entry} | (_closure(entry, forward) & rework)
        lanes = {lane_index.get(i) for i in chain | set(parents[entry])}
        if len(lanes) < 2 or None in lanes:
            rework -= chain
    for node_id in sorted(rework, key=lambda i: (ranks[i], i)):
        ranks[node_id] = max(ranks[parent] for parent in parents[node_id])
    return rework


def _with_documents(process, nodes) -> set[str]:
    """Activities with a data object or store drawn under them."""
    documented = set()
    for node_id, node in nodes.items():
        if node.find(tag("dataInputAssociation")) is not None or node.find(tag("dataOutputAssociation")) is not None:
            documented.add(node_id)
    for association in process.findall(tag("association")):
        documented |= {association.get("sourceRef"), association.get("targetRef")} & nodes.keys()
    return documented


def _closure(start: str, forward) -> set[str]:
    seen, stack = set(), list(forward[start])
    while stack:
        node_id = stack.pop()
        if node_id not in seen:
            seen.add(node_id)
            stack.extend(forward[node_id])
    return seen
