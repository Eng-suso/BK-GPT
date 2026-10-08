"""Stable graph ranks; source XML order and incoming DI are irrelevant."""
from collections import deque

from .policy import local_name, tag


def rank_process(process, nodes: dict) -> tuple[dict[str, int], set[str], dict[str, list[str]]]:
    adjacency = {node_id: [] for node_id in nodes}
    flows = sorted(process.findall(tag("sequenceFlow")), key=lambda e: e.get("id", ""))
    for flow in flows:
        adjacency[flow.get("sourceRef")].append((flow.get("targetRef"), flow.get("id")))
    for node_id in adjacency:
        default = nodes[node_id].get("default")
        adjacency[node_id].sort(key=lambda pair: (pair[1] != default, pair[0], pair[1]))
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
    degree = {node_id: len(parents[node_id]) for node_id in nodes}
    ready = deque(sorted(node_id for node_id in nodes if degree[node_id] == 0))
    ranks = {node_id: 0 for node_id in nodes}
    while ready:
        source = ready.popleft()
        for target in forward[source]:
            ranks[target] = max(ranks[target], ranks[source] + (0 if nodes[target].get("attachedToRef") == source else 1))
            degree[target] -= 1
            if degree[target] == 0:
                ready.append(target)
    connected = {ref for flow in flows for ref in (flow.get("sourceRef"), flow.get("targetRef"))}
    isolated = sorted(i for i in nodes if i not in connected and local_name(nodes[i]) not in {"boundaryEvent", "startEvent", "endEvent"})
    for index, node_id in enumerate(isolated):
        ranks[node_id] = index
    # Boundary events leave their host rather than participating in the happy path.
    for node_id, node in nodes.items():
        if local_name(node) == "boundaryEvent":
            ranks[node_id] = ranks.get(node.get("attachedToRef"), ranks[node_id])
    return ranks, feedback, parents
