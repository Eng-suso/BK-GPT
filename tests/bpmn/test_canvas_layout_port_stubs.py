"""A node label never walls in the docking port of another shape.

Found by the golden set on plans extracted by a real LLM (Gemini): a gateway
label placed below its diamond rested on the top port of a data object just
underneath. The router could not leave that port and the whole layout failed
with "Nessun percorso ortogonale privo di ostacoli". Both golden cases, two
runs out of two.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.bpmn.canvas_layout.geometry import Box
from backend.bpmn.canvas_layout.labels import node_label
from backend.bpmn.canvas_layout.router import segment_hits_box

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "extracted_plans"

GATEWAY = Box(831, 252, 50, 50)
# The top port of a data object right below the gateway, and its first stretch.
DATA_OBJECT_STUB = [(856, 372), (856, 348)]


def test_without_stubs_the_label_sits_below_the_gateway():
    label = node_label(GATEWAY, "Importo e tipo di richiesta", set(), {"gw": GATEWAY}, {})

    assert label.y > GATEWAY.bottom, "below is the BPMN convention, and the default"


def test_a_label_does_not_rest_on_another_shape_s_port():
    label = node_label(
        GATEWAY, "Importo e tipo di richiesta", set(), {"gw": GATEWAY}, {}, stubs=[DATA_OBJECT_STUB]
    )

    assert not segment_hits_box(*DATA_OBJECT_STUB, label.expanded(4)), (
        "the router expands labels by 4: a label that touches the stub walls the port in"
    )


def test_when_crowded_a_free_port_beats_the_default_placement():
    # Every placement collides with something; only the stub-free ones may win.
    crowd = {f"n{i}": Box(GATEWAY.x - 400 + i * 40, GATEWAY.y - 200, 40, 600) for i in range(20)}
    label = node_label(
        GATEWAY,
        "Importo e tipo di richiesta",
        set(),
        {"gw": GATEWAY, **crowd},
        {},
        stubs=[DATA_OBJECT_STUB],
    )

    assert not segment_hits_box(*DATA_OBJECT_STUB, label.expanded(4))


def _reference_grid_cross(a, b, c, d):
    """The per-pair crossing rule the grid search used before `_GridIndex`."""
    if a[1] == b[1] and c[0] == d[0]:
        return min(a[0], b[0]) <= c[0] <= max(a[0], b[0]) and min(c[1], d[1]) < a[1] < max(c[1], d[1])
    if a[0] == b[0] and c[1] == d[1]:
        return min(a[1], b[1]) <= c[1] <= max(a[1], b[1]) and min(c[0], d[0]) < a[0] < max(c[0], d[0])
    return False


def _reference_cost(u, v, boxes, routes, gap):
    from itertools import pairwise

    from backend.bpmn.canvas_layout.router import _OVERLAP_WEIGHT, _overlap

    if any(segment_hits_box(u, v, box) for box in boxes):
        return None
    return sum(
        _reference_grid_cross(u, v, w, z) + _overlap(u, v, w, z, gap) * _OVERLAP_WEIGHT
        for route in routes
        for w, z in pairwise(route)
    )


def test_the_grid_index_gives_the_cost_the_per_pair_formulas_gave():
    """Speed only: the routes a diagram gets must not change by one pixel."""
    import random

    from backend.bpmn.canvas_layout.router import _GridIndex

    rng = random.Random(20261031)
    # A coarse lattice, so that touching ends, shared lines and equal
    # coordinates - the edge cases - happen often.
    def coordinate():
        return rng.randrange(0, 12) * 10

    def orthogonal_route():
        point = (coordinate(), coordinate())
        route = [point]
        for step in range(rng.randrange(1, 5)):
            point = (coordinate(), point[1]) if step % 2 == 0 else (point[0], coordinate())
            route.append(point)
        return route

    for _ in range(300):
        boxes = [Box(coordinate(), coordinate(), rng.randrange(1, 4) * 10, rng.randrange(1, 4) * 10) for _ in range(rng.randrange(0, 4))]
        routes = [orthogonal_route() for _ in range(rng.randrange(0, 5))]
        index = _GridIndex(boxes, routes)
        for _ in range(20):
            u = (coordinate(), coordinate())
            v = (coordinate(), u[1]) if rng.random() < 0.5 else (u[0], coordinate())
            if u == v:
                continue
            gap = rng.choice([0, 5, 10])
            assert index.cost(u, v, gap) == _reference_cost(u, v, boxes, routes, gap), (u, v, boxes, routes, gap)


@pytest.mark.parametrize("plan", sorted(FIXTURES.glob("*.plan.json")), ids=lambda path: path.stem)
def test_plans_extracted_by_a_real_llm_compile_to_a_drawable_diagram(plan):
    from backend.bpmn import build_bpmn_semantic_model, semantic_model_to_bpmn_xml
    from backend.bpmn.canvas_layout import lint_visual_model
    from backend.process_understanding import ProcessUnderstanding

    understanding = ProcessUnderstanding.model_validate(json.loads(plan.read_text(encoding="utf-8")))
    model = build_bpmn_semantic_model(process_id="Process_replay", process_name=plan.stem, process=understanding)

    xml = semantic_model_to_bpmn_xml(model)

    import xml.etree.ElementTree as ET

    assert lint_visual_model(ET.fromstring(xml))["valid"]
