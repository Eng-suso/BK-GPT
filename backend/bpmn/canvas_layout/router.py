"""Deterministic orthogonal routing around node and label obstacles."""
from heapq import heappop, heappush
from itertools import pairwise

from .policy import ENTERPRISE_POLICY

_OVERLAP_WEIGHT = 100


def segment_hits_box(a, b, box):
    if a[0] == b[0]:
        return box.x < a[0] < box.right and max(min(a[1], b[1]), box.y) < min(max(a[1], b[1]), box.bottom)
    if a[1] == b[1]:
        return box.y < a[1] < box.bottom and max(min(a[0], b[0]), box.x) < min(max(a[0], b[0]), box.right)
    return True


def compress(points):
    result = []
    for point in points:
        if result and point == result[-1]:
            continue
        if len(result) >= 2 and ((point[0] == result[-1][0] == result[-2][0]) or (point[1] == result[-1][1] == result[-2][1])):
            result.pop()
        result.append(point)
    return result


def orthogonal_route(source_id, target_id, boxes, labels, previous=(), downward=False, ports=None):
    """Route a connection between two nodes.

    `ports` is the `(source, target)` pair of docking ports the flow must use;
    without it the flow leaves the source's right side (its bottom when
    `downward`) and enters the target's left side.
    """
    p = ENTERPRISE_POLICY
    source, target = boxes[source_id], boxes[target_id]
    if ports is not None:
        (a, out_normal), (b, in_normal) = (ports[0].point, ports[0].normal), (ports[1].point, ports[1].normal)
    else:
        a, out_normal = ((source.center[0], source.bottom), (0, 1)) if downward else ((source.right, source.center[1]), (1, 0))
        b, in_normal = (target.x, target.center[1]), (-1, 0)
    start = (a[0] + out_normal[0] * p.route_clearance, a[1] + out_normal[1] * p.route_clearance)
    finish = (b[0] + in_normal[0] * p.route_clearance, b[1] + in_normal[1] * p.route_clearance)
    obstacles = [box if key in {source_id, target_id} else box.expanded(p.route_clearance) for key, box in boxes.items()]
    obstacles += [box.expanded(4) for box in labels.values()]
    # Past its docking stub a route keeps clear of its own two shapes too, so
    # it never grazes a vertex where another flow docks.
    ends = [boxes[key].expanded(p.route_clearance - 1) for key in {source_id, target_id}]
    alongside = p.route_clearance / 2

    def free(u, v, boxes_in_way):
        return not any(segment_hits_box(u, v, box) for box in boxes_in_way)

    def clear(points):
        segments = list(pairwise(points))
        return all(free(u, v, obstacles) for u, v in segments) and all(free(u, v, ends) for u, v in segments[1:-1])

    def contacts(points):
        """Crossings with the routes already drawn, a shared stretch weighing as many crossings.

        A crossing is tolerated when unavoidable; two flows running on one line
        read as a single flow, so that is never the cheaper choice.
        """
        return sum(
            _cross(u, v, w, z) + _overlap(u, v, w, z, alongside) * _OVERLAP_WEIGHT
            for u, v in pairwise(points) for other in previous for w, z in pairwise(other)
        )

    def cost(points):
        length = sum(abs(u[0] - v[0]) + abs(u[1] - v[1]) for u, v in pairwise(points))
        return length + max(0, len(points) - 2) * p.bend_cost + contacts(points) * p.crossing_cost

    candidates = [[a, b]] if _straight(a, b, out_normal, in_normal) else []
    middle_x = (start[0] + finish[0]) / 2
    candidates.extend([
        [a, start, (middle_x, start[1]), (middle_x, finish[1]), finish, b],
        [a, start, (start[0], finish[1]), finish, b],
        [a, start, (finish[0], start[1]), finish, b],
    ])
    # Lanes parallel to the ends give a flow that leaves next to an earlier one
    # (two boundary events on one task) a corridor of its own.
    lanes = [step * p.route_clearance * 2 for step in (-3, -2, -1, 1, 2, 3)]
    ys = sorted({box.y - p.route_clearance for box in boxes.values()} | {box.bottom + p.route_clearance for box in boxes.values()}
                | {end[1] + lane for end in (start, finish) for lane in lanes})
    candidates.extend([a, start, (start[0], y), (finish[0], y), finish, b] for y in ys)
    # Vertical channels next to the nodes, and beside the midline, so a flow
    # never has to share its stretch with one routed before it.
    xs = sorted({box.x - p.route_clearance for box in boxes.values()} | {box.right + p.route_clearance for box in boxes.values()}
                | {middle_x + lane for lane in lanes} | {end[0] + lane for end in (start, finish) for lane in lanes})
    candidates.extend([a, start, (x, start[1]), (x, finish[1]), finish, b] for x in xs)
    viable = [compress(path) for path in candidates if clear(path)]
    best = min(viable, key=lambda path: (cost(path), path)) if viable else None
    if best is not None and not contacts(best):
        return best
    # Obstacle-corner visibility grid is a bounded fallback for complex paths.
    # Common linear and cross-lane paths use the candidates above.
    xs = sorted({start[0], finish[0]} | {value for box in obstacles for value in (box.x, box.right)})
    ys = sorted({start[1], finish[1]} | {value for box in obstacles for value in (box.y, box.bottom)})
    origin = (xs.index(start[0]), ys.index(start[1]), 2)
    queue, distance, parent = [(0, origin)], {origin: 0}, {}
    goal = None
    # A grid segment is open or closed, and touches earlier routes so many
    # times, whatever direction the search reaches it from. Each one is
    # reached from up to three directions and from both ends: computing it
    # once per call kept the answer and took a dense real plan (19 steps, 29
    # flows) from minutes to seconds.
    segment_costs = {}
    grid_index = _GridIndex([*obstacles, *ends], previous)

    def segment_cost(u, v):
        key = (u, v) if u <= v else (v, u)
        if key not in segment_costs:
            segment_costs[key] = grid_index.cost(key[0], key[1], alongside)
        return segment_costs[key]
    while queue:
        value, current = heappop(queue)
        if value != distance[current]:
            continue
        x, y, direction = current
        if (xs[x], ys[y]) == finish:
            goal = current
            break
        for nx, ny, next_direction in ((x-1, y, 0), (x+1, y, 0), (x, y-1, 1), (x, y+1, 1)):
            if not (0 <= nx < len(xs) and 0 <= ny < len(ys)):
                continue
            u, v = (xs[x], ys[y]), (xs[nx], ys[ny])
            # Grid segments end at obstacle corners; charge a crossing even
            # when it falls exactly on a grid vertex, before compression.
            touches = segment_cost(u, v)
            if touches is None:
                continue
            next_value = value + abs(u[0]-v[0]) + abs(u[1]-v[1]) + touches * p.crossing_cost + (p.bend_cost if direction not in {2, next_direction} else 0)
            nxt = (nx, ny, next_direction)
            if next_value < distance.get(nxt, float("inf")):
                distance[nxt], parent[nxt] = next_value, current
                heappush(queue, (next_value, nxt))
    if goal is None and best is not None:
        return best
    if goal is None:
        raise ValueError(f"Nessun percorso ortogonale privo di ostacoli: {source_id} → {target_id}.")
    path = []
    while goal != origin:
        path.append((xs[goal[0]], ys[goal[1]]))
        goal = parent[goal]
    path.append(start)
    routed = compress([a, *reversed(path), b])
    return min([best, routed], key=lambda path: (cost(path), path)) if best else routed


class _GridIndex:
    """The obstacles and earlier routes, pre-split for one grid search.

    The grid search asks the same question for every segment between two
    adjacent grid points: is it free of `boxes`, and how many times does it
    touch `routes`? Asked through `segment_hits_box`, a crossing test and
    `_overlap` that is three Python calls per pair, and a dense real plan
    asked it some 250 million times. Here the same comparisons run inline on
    plain tuples sorted once by orientation. A grid segment always has a
    length, so only its two orthogonal cases exist; a degenerate earlier
    segment (a point) never crosses nor overlaps anything and is left out.

    A grid crossing counts also when the earlier route meets the segment
    exactly at one of its ends: grid segments end at obstacle corners, and a
    crossing there would vanish once the path is compressed.
    `tests/bpmn/test_canvas_layout_port_stubs.py` keeps the per-pair formulas
    this replaced and checks both give the same cost.
    """

    def __init__(self, boxes, routes):
        self.boxes = [(box.x, box.right, box.y, box.bottom) for box in boxes]
        self.horizontal, self.vertical = [], []
        for route in routes:
            for w, z in pairwise(route):
                if w == z:
                    continue
                if w[1] == z[1]:
                    self.horizontal.append((w[1], min(w[0], z[0]), max(w[0], z[0])))
                elif w[0] == z[0]:
                    self.vertical.append((w[0], min(w[1], z[1]), max(w[1], z[1])))

    def cost(self, u, v, gap):
        """`None` when the segment `u`-`v` is blocked, else its weighted contacts.

        Same value as `segment_hits_box` over the boxes, and grid crossings
        plus `_overlap * _OVERLAP_WEIGHT` summed over the routes.
        """
        if u[1] == v[1]:
            y, x1, x2 = u[1], min(u[0], v[0]), max(u[0], v[0])
            for bx, br, by, bb in self.boxes:
                if by < y < bb and max(x1, bx) < min(x2, br):
                    return None
            crossings = sum(1 for x, y1, y2 in self.vertical if x1 <= x <= x2 and y1 < y < y2)
            overlaps = sum(
                1 for py, px1, px2 in self.horizontal if abs(y - py) <= gap and min(x2, px2) - max(x1, px1) > 0
            )
        else:
            x, y1, y2 = u[0], min(u[1], v[1]), max(u[1], v[1])
            for bx, br, by, bb in self.boxes:
                if bx < x < br and max(y1, by) < min(y2, bb):
                    return None
            crossings = sum(1 for py, px1, px2 in self.horizontal if y1 <= py <= y2 and px1 < x < px2)
            overlaps = sum(
                1 for px, py1, py2 in self.vertical if abs(x - px) <= gap and min(y2, py2) - max(y1, py1) > 0
            )
        return crossings + overlaps * _OVERLAP_WEIGHT


def _straight(a, b, out_normal, in_normal):
    """True when one segment leaves `a` along its port and enters `b` along its port."""
    if a[0] != b[0] and a[1] != b[1]:
        return False
    step = ((b[0] > a[0]) - (b[0] < a[0]), (b[1] > a[1]) - (b[1] < a[1]))
    return step == out_normal == (-in_normal[0], -in_normal[1])


def _overlap(a, b, c, d, gap=0.0):
    """True when two segments run along one line for a stretch (not just touch at a point).

    With `gap`, parallel segments closer than that count too: a few pixels
    apart they still read as one line.
    """
    if a[1] == b[1] and c[1] == d[1] and abs(a[1] - c[1]) <= gap:
        return min(max(a[0], b[0]), max(c[0], d[0])) - max(min(a[0], b[0]), min(c[0], d[0])) > 0
    if a[0] == b[0] and c[0] == d[0] and abs(a[0] - c[0]) <= gap:
        return min(max(a[1], b[1]), max(c[1], d[1])) - max(min(a[1], b[1]), min(c[1], d[1])) > 0
    return False


def _cross(a, b, c, d):
    if a[1] == b[1] and c[0] == d[0]:
        return min(a[0], b[0]) < c[0] < max(a[0], b[0]) and min(c[1], d[1]) < a[1] < max(c[1], d[1])
    if a[0] == b[0] and c[1] == d[1]:
        return _cross(c, d, a, b)
    return False
