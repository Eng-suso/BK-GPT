"""Deterministic branch labels placed beside routes, clear of nodes and text."""
from itertools import pairwise

from .geometry import Box
from .router import segment_hits_box


def branch_label(points, name, boxes, labels, routes, container=None, lane_boundaries=()):
    width = min(140, max(44, len(name) * 6))
    height = 30 if len(name) <= 22 else 44
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
