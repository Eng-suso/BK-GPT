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
