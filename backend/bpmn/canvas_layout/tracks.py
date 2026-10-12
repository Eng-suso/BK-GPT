"""Rows inside a lane: the main path stays on one straight track, branches step aside.

Reference models (BPMN 2.0 by Example, OMG) keep the path a case usually takes
on one horizontal line and draw every alternative branch on a track of its
own beside it. Each node inherits the track of the parent it continues; a
gateway's main successor (the one with the longest way still ahead, then the
default flow) continues the gateway's track and the other successors take the
nearest free track below, then above.
"""
from .policy import local_name, tag


def assign_tracks(process, nodes, ranks, feedback, owner) -> dict[str, int]:
    """Track (row offset from the lane's main line) of every node that is not a boundary event."""
    children: dict[str, list[tuple[str, str]]] = {node_id: [] for node_id in nodes}
    for flow in process.findall(tag("sequenceFlow")):
        source, target = flow.get("sourceRef"), flow.get("targetRef")
        if flow.get("id") not in feedback and source in nodes and target in nodes:
            children[source].append((target, flow.get("id", "")))
    for node_id, node in nodes.items():
        host = node.get("attachedToRef")
        if local_name(node) == "boundaryEvent" and host in children:
            children[host].append((node_id, ""))

    ahead: dict[str, int] = {}
    for node_id in sorted(nodes, key=lambda i: -ranks[i]):
        ahead[node_id] = max((ahead.get(target, 0) + 1 for target, _ in children[node_id]), default=0)

    def main_child(node_id: str) -> str | None:
        default = nodes[node_id].get("default")
        ordinary = [(target, flow_id) for target, flow_id in children[node_id] if local_name(nodes[target]) != "boundaryEvent"]
        best = min(ordinary, key=lambda pair: (-ahead[pair[0]], pair[1] != default, pair[1]), default=None)
        return best[0] if best else None

    mains = {node_id: main_child(node_id) for node_id in nodes}
    parents: dict[str, list[str]] = {node_id: [] for node_id in nodes}
    for source, pairs in children.items():
        for target, _ in pairs:
            parents[target].append(source)

    tracks: dict[str, int] = {}
    taken: set[tuple[str | None, int, int]] = set()
    for node_id in sorted(nodes, key=lambda i: (ranks[i], i)):
        node = nodes[node_id]
        if local_name(node) == "boundaryEvent":
            tracks[node_id] = tracks.get(node.get("attachedToRef"), 0)
            continue
        band = owner.get(node_id)
        placed = [parent for parent in parents[node_id] if parent in tracks]
        continued = [parent for parent in placed if mains.get(parent) == node_id and owner.get(parent) == band]
        if continued:
            desired = min((tracks[parent] for parent in continued), key=lambda track: (abs(track), track))
            steps = (0, 1, -1, 2, -2, 3, -3)
        elif placed:
            # A branch: beside the track it leaves, below first.
            parent = max(placed, key=lambda i: (ranks[i], i))
            desired = tracks[parent] if owner.get(parent) == band else 0
            steps = (0, 1, -1, 2, -2, 3, -3) if owner.get(parent) != band else (1, -1, 2, -2, 3, -3)
        else:
            desired, steps = 0, (0, 1, -1, 2, -2, 3, -3)
        track = next(
            (desired + step for step in steps if (band, ranks[node_id], desired + step) not in taken),
            max((t for b, r, t in taken if b == band and r == ranks[node_id]), default=0) + 1,
        )
        taken.add((band, ranks[node_id], track))
        tracks[node_id] = track
    return tracks
