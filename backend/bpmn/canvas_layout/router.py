"""Deterministic orthogonal routing around node and label obstacles."""
from heapq import heappop, heappush
from itertools import pairwise

from .policy import ENTERPRISE_POLICY


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


def orthogonal_route(source_id, target_id, boxes, labels, previous=(), downward=False):
    p = ENTERPRISE_POLICY
    source, target = boxes[source_id], boxes[target_id]
    a = (source.center[0], source.bottom) if downward else (source.right, source.center[1])
    b = (target.x, target.center[1])
    start = (a[0], a[1] + p.route_clearance) if downward else (a[0] + p.route_clearance, a[1])
    finish = (b[0] - p.route_clearance, b[1])
    obstacles = [box if key in {source_id, target_id} else box.expanded(p.route_clearance) for key, box in boxes.items()]
    obstacles += [box.expanded(4) for key, box in labels.items() if key not in {source_id, target_id}]

    def clear(points):
        return all(not segment_hits_box(u, v, box) for u, v in pairwise(points) for box in obstacles)

    def cost(points):
        length = sum(abs(u[0] - v[0]) + abs(u[1] - v[1]) for u, v in pairwise(points))
        crossings = sum(_cross(u, v, w, z) for u, v in pairwise(points) for other in previous for w, z in pairwise(other))
        return length + max(0, len(points) - 2) * p.bend_cost + crossings * p.crossing_cost

    candidates = [[a, b]] if a[0] == b[0] or a[1] == b[1] else []
    middle_x = (start[0] + finish[0]) / 2
    candidates.extend([
        [a, start, (middle_x, start[1]), (middle_x, finish[1]), finish, b],
        [a, start, (start[0], finish[1]), finish, b],
        [a, start, (finish[0], start[1]), finish, b],
    ])
    ys = sorted({box.y - p.route_clearance for box in boxes.values()} | {box.bottom + p.route_clearance for box in boxes.values()})
    candidates.extend([a, start, (start[0], y), (finish[0], y), finish, b] for y in ys)
    viable = [compress(path) for path in candidates if clear(path)]
    if viable:
        return min(viable, key=lambda path: (cost(path), path))
    # Obstacle-corner visibility grid is a bounded fallback for complex paths.
    # Common linear and cross-lane paths use the candidates above.
    xs = sorted({start[0], finish[0]} | {value for box in obstacles for value in (box.x, box.right)})
    ys = sorted({start[1], finish[1]} | {value for box in obstacles for value in (box.y, box.bottom)})
    origin = (xs.index(start[0]), ys.index(start[1]), 2)
    queue, distance, parent = [(0, origin)], {origin: 0}, {}
    goal = None
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
            if not clear([u, v]):
                continue
            next_value = value + cost([u, v]) + (p.bend_cost if direction not in {2, next_direction} else 0)
            nxt = (nx, ny, next_direction)
            if next_value < distance.get(nxt, float("inf")):
                distance[nxt], parent[nxt] = next_value, current
                heappush(queue, (next_value, nxt))
    if goal is None:
        raise ValueError(f"Nessun percorso ortogonale privo di ostacoli: {source_id} → {target_id}.")
    path = []
    while goal != origin:
        path.append((xs[goal[0]], ys[goal[1]]))
        goal = parent[goal]
    path.append(start)
    return compress([a, *reversed(path), b])


def _cross(a, b, c, d):
    if a[1] == b[1] and c[0] == d[0]:
        return min(a[0], b[0]) < c[0] < max(a[0], b[0]) and min(c[1], d[1]) < a[1] < max(c[1], d[1])
    if a[0] == b[0] and c[1] == d[1]:
        return _cross(c, d, a, b)
    return False
