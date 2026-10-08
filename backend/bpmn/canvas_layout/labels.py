"""Deterministic branch labels placed beside routes, clear of nodes and text."""
from itertools import pairwise

from .geometry import Box
from .router import segment_hits_box


def branch_label(points, name, boxes, labels, routes):
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
    for candidate in candidates:
        if any(_overlap(candidate.expanded(4), box) for box in [*boxes.values(), *labels.values()]):
            continue
        if any(segment_hits_box(a, b, candidate.expanded(2)) for route in [*routes, points] for a, b in pairwise(route)):
            continue
        return candidate
    raise ValueError(f"Nessuno spazio leggibile per l'etichetta del ramo: {name}.")


def _overlap(a, b):
    return a.x < b.right and a.right > b.x and a.y < b.bottom and a.bottom > b.y
