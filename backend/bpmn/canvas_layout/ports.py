"""Docking ports: every sequence flow leaves and enters a node through its own side.

Two flows sharing one docking point read as one line that forks or merges on
the shape itself, which modelling guidelines rule out: a gateway's branches
leave from distinct vertices, and a rework flow enters a task from another side
than the forward flow. Each node hands out its four sides (the vertices of a
gateway diamond, the edge midpoints of a task or event) one flow at a time:
outgoing flows first, the straightest one taking the right side, then incoming
flows, the straightest taking the left side. A gateway branch that is not
level with the diamond leaves from the vertex facing its target (top or
bottom), as in the OMG reference diagrams: through the right vertex it would
have to bend on the shape and its label would float away from it.
"""
from dataclasses import dataclass

from .geometry import Box

SIDES = ("right", "left", "top", "bottom")
NORMAL = {"right": (1, 0), "left": (-1, 0), "top": (0, -1), "bottom": (0, 1)}


@dataclass(frozen=True)
class Port:
    point: tuple[float, float]
    side: str

    @property
    def normal(self) -> tuple[int, int]:
        return NORMAL[self.side]


def side_point(box: Box, side: str, offset: float = 0.0) -> tuple[float, float]:
    """The midpoint of `side`, moved by `offset` (a fraction of the side) along it."""
    cx, cy = box.center
    dx, dy = box.width * offset, box.height * offset
    return {"right": (box.right, cy + dy), "left": (box.x, cy + dy), "top": (cx + dx, box.y), "bottom": (cx + dx, box.bottom)}[side]


def assign_ports(
    flows: list[tuple[str, str, str]],
    boxes: dict[str, Box],
    attachments: list[tuple[str, str, str]] = (),
    reserved: dict[str, set[str]] | None = None,
    pools: dict[str, Box] | None = None,
    gateways: set[str] | frozenset[str] = frozenset(),
) -> dict[str, tuple[Port, Port]]:
    """Give each `(flow_id, source, target)` a source and a target port, never shared on a node.

    Sequence flows take whole sides. `attachments` (data associations, message
    flows) take the side facing the other end; when a sequence flow holds it,
    they dock a quarter of the way along it instead. A message flow meets a
    collapsed pool (`pools`) straight above or below the shape it connects.
    `reserved` sides are never handed out (a boundary event sits on its host's
    bottom edge).
    """
    reserved = reserved or {}
    pools = pools or {}
    used: dict[str, set[str]] = {node: set(sides) for node, sides in reserved.items()}

    def take(node: str, preferences: tuple[str, ...]) -> str:
        taken = used.setdefault(node, set())
        free = [side for side in preferences if side not in taken]
        side = free[0] if free else next(side for side in preferences if side not in reserved.get(node, ()))
        taken.add(side)
        return side

    def vertical(dy: float) -> tuple[str, str]:
        # Level flows go over the top: event and gateway labels sit underneath.
        return ("top", "bottom") if dy <= 0 else ("bottom", "top")

    def straightness(source: str, target: str) -> tuple[bool, float, float]:
        (sx, sy), (tx, ty) = boxes[source].center, boxes[target].center
        # forward before backward, then the most level, then the nearest
        return (tx < sx, abs(ty - sy), abs(tx - sx))

    ordered = sorted(flows, key=lambda flow: straightness(flow[1], flow[2]))
    sides: dict[str, tuple[str, str]] = {}
    out_side: dict[str, str] = {}
    # A backward flow (rework loop) runs over the top of the forward path, as
    # in reference models: from below it would cut the branches it loops past.
    for flow_id, source, target in ordered:
        (sx, sy), (tx, ty) = boxes[source].center, boxes[target].center
        near, far = vertical(ty - sy)
        level = abs(ty - sy) <= boxes[source].height / 2
        stacked = abs(tx - sx) <= min(boxes[source].width, boxes[target].width) / 2
        if stacked and not level:
            # Same column (a rework loop kept local): straight up or down.
            preferences = (near, far, "right")
        elif tx < sx and not level:
            # A return to another row leaves sideways, toward the activity it repeats.
            preferences = ("left", near, "top")
        elif tx < sx:
            preferences = ("top", "bottom", "right")
        elif source in gateways and not level:
            preferences = (near, "right", far)
        else:
            preferences = ("right", near, far)
        out_side[flow_id] = take(source, preferences)
    for flow_id, source, target in ordered:
        (sx, sy), (tx, ty) = boxes[source].center, boxes[target].center
        near, far = vertical(sy - ty)
        stacked = abs(tx - sx) <= min(boxes[source].width, boxes[target].width) / 2
        level = abs(ty - sy) <= boxes[target].height / 2
        if stacked and not level:
            entry = (near, far, "left")
        elif tx >= sx:
            entry = ("left", near, far)
        else:
            entry = (near, "top", "bottom", "left") if not level else ("top", "bottom", "left")
        sides[flow_id] = (out_side[flow_id], take(target, entry))
    ports = {
        flow_id: (Port(side_point(boxes[source], out), out), Port(side_point(boxes[target], into), into))
        for flow_id, source, target in flows
        for out, into in [sides[flow_id]]
    }

    shared: dict[tuple[str, str], int] = {}

    def attach(node: str, other: tuple[float, float]) -> Port:
        box = boxes[node]
        (nx, ny), (ox, oy) = box.center, other
        horizontal = ("right", "left") if ox >= nx else ("left", "right")
        upright = ("bottom", "top") if oy >= ny else ("top", "bottom")
        side = (upright if abs(oy - ny) > abs(ox - nx) else horizontal)[0]
        if side in reserved.get(node, ()):
            side = horizontal[0] if side in upright else upright[0]
        if side not in used.setdefault(node, set()):
            used[node].add(side)
            return Port(side_point(box, side), side)
        # The side already carries a flow: dock beside it, toward the other end.
        count = shared[node, side] = shared.get((node, side), 0) + 1
        toward = (ox >= nx) if side in {"top", "bottom"} else (oy >= ny)
        offset = 0.25 * (1 if toward == (count % 2 == 1) else -1)
        return Port(side_point(box, side, offset), side)

    for flow_id, source, target in attachments:
        if source in pools and target in pools:
            continue  # pool to pool: the router's default sides
        if target in pools or source in pools:
            node, pool = (source, pools[target]) if target in pools else (target, pools[source])
            side = "bottom" if pool.y >= boxes[node].bottom else "top"
            node_port = attach(node, (boxes[node].center[0], pool.center[1]))
            edge = (node_port.point[0], pool.y if side == "bottom" else pool.bottom)
            pool_port = Port(edge, "top" if side == "bottom" else "bottom")
            ports[flow_id] = (node_port, pool_port) if target in pools else (pool_port, node_port)
            continue
        ports[flow_id] = (attach(source, boxes[target].center), attach(target, boxes[source].center))
    return ports
