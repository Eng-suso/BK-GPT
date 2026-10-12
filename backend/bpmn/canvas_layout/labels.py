"""Deterministic branch labels placed beside routes, clear of nodes and text."""
from itertools import pairwise
from math import ceil

from .geometry import Box
from .router import segment_hits_box


def label_size(name):
    """Width and height a label needs: one line up to 22 characters, two beyond."""
    return min(140, max(44, len(name) * 6)), 30 if len(name) <= 22 else 44


def branch_label(points, name, boxes, labels, routes, container=None, lane_boundaries=()):
    width, height = label_size(name)
    candidates = []
    for a, b in pairwise(points):
        cx, cy = (a[0]+b[0])/2, (a[1]+b[1])/2
        for gap in (8, 20, 36, 52, 68, 100, 140):
            if a[1] == b[1]:
                candidates += [Box(cx-width/2, cy-height-gap, width, height), Box(cx-width/2, cy+gap, width, height)]
            else:
                candidates += [Box(cx+gap, cy-height/2, width, height), Box(cx-width-gap, cy-height/2, width, height)]
    # Dense real-world diagrams may reserve the segment midpoint for another
    # branch label. Search nearby along the same segment before adding space
    # to the diagram or giving up. Keep the closest placements first.
    for a, b in pairwise(points):
        cx, cy = (a[0]+b[0])/2, (a[1]+b[1])/2
        for shift in (24, -24, 48, -48, 72, -72, 96, -96):
            for gap in (8, 20, 36, 52, 68, 100, 140):
                if a[1] == b[1]:
                    candidates += [Box(cx+shift-width/2, cy-height-gap, width, height), Box(cx+shift-width/2, cy+gap, width, height)]
                else:
                    candidates += [Box(cx+gap, cy+shift-height/2, width, height), Box(cx-width-gap, cy+shift-height/2, width, height)]
    candidates.sort(key=lambda box: _distance_to_route(box, points))
    for candidate in candidates:
        if container and not (container.x <= candidate.x and container.y <= candidate.y and container.right >= candidate.right and container.bottom >= candidate.bottom):
            continue
        if any(_overlap(candidate.expanded(4), box) for box in [*boxes.values(), *labels.values()]):
            continue
        if any(_crosses_lane_border(candidate, lane) for lane in lane_boundaries):
            continue
        if any(segment_hits_box(a, b, candidate.expanded(2)) for route in [*routes, points] for a, b in pairwise(route)):
            continue
        return candidate
    raise ValueError(f"Nessuno spazio leggibile per l'etichetta del ramo: {name}.")


def node_label(box, name, docked_sides, boxes, labels, container=None, lane_boundaries=(), turns=()):
    """Place an event or gateway label beside its shape, clear of where its flows run.

    Below is the BPMN convention; when a flow docks there the label moves
    above, then to a corner. `turns` holds the corners, as `(horizontal,
    vertical)` sides, that a docked flow bends through on its way to a node
    off both axes; they are a last resort. The first placement that stays
    inside the pool, off lane borders and clear of nodes and labels wins; a
    long name that fits nowhere on two lines is tried again, narrower.
    """
    gap = 8
    sizes = [label_size(name)]
    if sizes[0][0] > _NARROW:
        sizes.append((_NARROW, 16 + 14 * ceil(len(name) * 6 / _NARROW)))
    candidates = [
        candidate
        for width, height in sizes
        for candidate in _node_label_candidates(box, width, height, gap, docked_sides, turns)
    ]
    for candidate in candidates:
        if container and not (container.x <= candidate.x and container.y <= candidate.y and container.right >= candidate.right and container.bottom >= candidate.bottom):
            continue
        if any(_overlap(candidate.expanded(4), other) for other in [*boxes.values(), *labels.values()] if other != box):
            continue
        if any(_crosses_lane_border(candidate, lane) for lane in lane_boundaries):
            continue
        return candidate
    # Crowded: keep at least the sides the flows dock on free.
    return candidates[0]


_NARROW = 100


def _node_label_candidates(box, width, height, gap, docked_sides, turns):
    cx = box.center[0]
    placements = {
        "bottom": Box(cx - width / 2, box.bottom + gap, width, height),
        "top": Box(cx - width / 2, box.y - gap - height, width, height),
    }
    corners = {
        ("left", "bottom"): Box(box.x - width - gap / 2, box.bottom + gap / 2, width, height),
        ("right", "bottom"): Box(box.right + gap / 2, box.bottom + gap / 2, width, height),
        ("left", "top"): Box(box.x - width - gap / 2, box.y - height - gap / 2, width, height),
        ("right", "top"): Box(box.right + gap / 2, box.y - height - gap / 2, width, height),
    }
    return [
        *(placements[side] for side in ("bottom", "top") if side not in docked_sides),
        *(corner for key, corner in corners.items() if key not in turns),
        *(corner for key, corner in corners.items() if key in turns),  # the route bends around it
    ]


def _overlap(a, b):
    return a.x < b.right and a.right > b.x and a.y < b.bottom and a.bottom > b.y


def _crosses_lane_border(label, lane, margin=4):
    return label.x < lane.right and label.right > lane.x and any(
        label.y < border + margin and label.bottom > border - margin
        for border in (lane.y, lane.bottom)
    )


def _distance_to_route(label, points):
    cx, cy = label.center
    return min(
        abs(cx - min(max(cx, min(a[0], b[0])), max(a[0], b[0])))
        + abs(cy - min(max(cy, min(a[1], b[1])), max(a[1], b[1])))
        + .2 * (abs(cx - (a[0] + b[0]) / 2) + abs(cy - (a[1] + b[1]) / 2))
        for a, b in pairwise(points)
    )
