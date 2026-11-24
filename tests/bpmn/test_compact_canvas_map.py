"""Navigation map keeps exact edit targets without exposing whole XML."""

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from backend.bpmn.compact_canvas_map import BPMN_NS, compact_canvas_map

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "purchase_layout.bpmn"


def test_map_lists_every_semantic_id_and_control_edge():
    xml = FIXTURE.read_text(encoding="utf-8")
    root = ET.fromstring(xml)
    lines = [line.split("\t") for line in compact_canvas_map(xml).splitlines()[2:]]
    mapped_ids = {line[1] for line in lines if line[0] in {"N", "F"}}
    semantic_ids = {element.attrib["id"] for element in root.iter()
                    if element.tag.startswith("{" + BPMN_NS + "}") and "id" in element.attrib}
    assert mapped_ids == semantic_ids
    expected_edges = {(flow.get("id"), flow.get("sourceRef"), flow.get("targetRef"))
                      for flow in root.iter("{" + BPMN_NS + "}sequenceFlow")}
    mapped_edges = {(line[1], line[2], line[3]) for line in lines if line[0] == "F"}
    assert expected_edges <= mapped_edges
    assert "<bpmn" not in compact_canvas_map(xml)


def test_map_escapes_labels_and_rejects_entities():
    xml = ('<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL" id="D">'
           '<process id="P"><task id="T" name="Line&#10;two&#9;tab"/></process></definitions>')
    assert "Line\\ntwo\\ttab" in compact_canvas_map(xml)
    with pytest.raises(ValueError):
        compact_canvas_map('<!DOCTYPE x [<!ENTITY e "unsafe">]><x>&e;</x>')


def test_map_operation_uses_live_canvas_without_database_write(monkeypatch):
    from backend.toolsets import bpmn as canvas_tools

    xml = FIXTURE.read_text(encoding="utf-8")
    monkeypatch.setattr(canvas_tools, "_state_or_saved_canvas_xml", lambda *_args: (xml, "live_canvas"))
    monkeypatch.setattr(canvas_tools.workspace_database, "update_bpmn_model",
                        lambda *_args, **_kwargs: pytest.fail("map attempted a database write"))
    result = canvas_tools.manage_canvas_bpmn_model.func(
        bpmn_model_id="model-1", operation="map", state={}, tool_call_id="call-1",
    )
    assert "canvas-map 1" in str(result)
    assert "<definitions" not in str(result)
