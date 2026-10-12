"""The layout reproduces the drawing of a reference model from "BPMN 2.0 by Example" (OMG).

The "Issue list" process keeps the path a case usually takes on one straight
line, drops the alternative branch onto a track below, returns the loop over
the top and docks every flow on its own side of a shape.
"""
import xml.etree.ElementTree as ET
from pathlib import Path

from backend.bpmn.canvas_layout import apply_enterprise_layout, lint_visual_model

BPMNDI = "{http://www.omg.org/spec/BPMN/20100524/DI}"
DC = "{http://www.omg.org/spec/DD/20100524/DC}"
DI = "{http://www.omg.org/spec/DD/20100524/DI}"


def _layout():
    root = ET.fromstring(apply_enterprise_layout(Path("tests/fixtures/omg_issue_list.bpmn").read_text(encoding="utf-8")))
    shapes = {
        shape.get("bpmnElement"): {key: float(value) for key, value in shape.find(f"{DC}Bounds").attrib.items()}
        for shape in root.iter(f"{BPMNDI}BPMNShape")
    }
    edges = {
        edge.get("bpmnElement"): [(float(point.get("x")), float(point.get("y"))) for point in edge.findall(f"{DI}waypoint")]
        for edge in root.iter(f"{BPMNDI}BPMNEdge")
    }
    return root, shapes, edges


def _center(box):
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def test_the_main_path_is_one_straight_line_and_the_alternative_drops_below():
    _, shapes, _ = _layout()

    main_line = {_center(shapes[node])[1] for node in ("Start", "Friday", "Check", "Active", "Send")}
    assert len(main_line) == 1
    assert _center(shapes["End"])[0] == _center(shapes["Send"])[0]
    assert _center(shapes["End"])[1] > main_line.pop()


def test_branches_leave_the_gateway_from_distinct_vertices_and_the_loop_runs_over_the_top():
    root, shapes, edges = _layout()

    active = shapes["Active"]
    assert edges["Yes"][0] == (active["x"] + active["width"], _center(active)[1])
    assert edges["No"][0] == (_center(active)[0], active["y"] + active["height"])
    friday, send = shapes["Friday"], shapes["Send"]
    assert edges["Loop"][0] == (_center(send)[0], send["y"])
    assert edges["Loop"][-1] == (_center(friday)[0], friday["y"])
    assert all(y <= friday["y"] for _, y in edges["Loop"])
    report = lint_visual_model(root)
    assert report["valid"] and report["warnings"] == [] and report["metrics"]["edge_crossings"] == 0
