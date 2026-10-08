"""Reproducible layout corpus: geometry quality, not live NLP accuracy."""
import xml.etree.ElementTree as ET

import pytest

from backend.bpmn.canvas_layout import apply_enterprise_layout, lint_visual_model
from tests.bpmn.test_canvas_layout_policy import NS, semantic, shapes


@pytest.mark.parametrize("case", range(100))
def test_generated_corpus_retains_topology_and_owners_without_visual_errors(case):
    count = 2 + case % 9
    roles = 1 + case % 4
    nodes = [("start", "startEvent", "Richiesta ricevuta")]
    nodes += [(f"task{i}", "serviceTask" if i % 3 == 0 else "userTask", f"Verificare documento {i}") for i in range(count)]
    nodes += [("end", "endEvent", "Esito registrato")]
    ids = [node[0] for node in nodes]
    flows = list(zip(ids, ids[1:], strict=False))
    if case % 3 == 0:
        # Fork/rejoin inside the process, preserving the ordinary happy path.
        nodes += [("branch", "userTask", "Confrontare evidenze")]
        flows += [("start", "branch"), ("branch", "end")]
    if case % 5 == 0:
        flows += [(f"task{count-1}", "task0")]
    lanes = [(f"role{i}", f"Responsabile {i}", [id for j, (id, _, _) in enumerate(nodes) if j % roles == i]) for i in range(roles)]
    original = semantic(nodes, flows, lanes)
    generated = apply_enterprise_layout(original)
    root = ET.fromstring(generated)
    report = lint_visual_model(root)
    assert report["valid"], report
    assert {(e.get("sourceRef"), e.get("targetRef")) for e in root.findall(".//b:sequenceFlow", NS)} == set(flows)
    assert {lane.get("id"): [ref.text for ref in lane.findall("b:flowNodeRef", NS)] for lane in root.findall(".//b:lane", NS)} == {id: members for id, _, members in lanes}
    assert apply_enterprise_layout(generated) == generated
    positioned = shapes(generated)
    assert positioned["start"]["x"] < positioned["end"]["x"]
    assert positioned["end"]["x"] > max(positioned[f"task{i}"]["x"] for i in range(count))


def test_long_nlp_activity_names_grow_vertically_without_overlapping_sibling_branches():
    name = "Verificare tutti i documenti ricevuti e confrontare le informazioni con le evidenze del processo " * 3
    nodes = [("s", "startEvent", ""), ("a", "userTask", name), ("b", "userTask", name), ("e", "endEvent", "")]
    xml = apply_enterprise_layout(semantic(nodes, [("s", "a"), ("s", "b"), ("a", "e"), ("b", "e")], [("role", "Acquisti", ["s", "a", "b", "e"])]))
    positioned = shapes(xml)
    assert positioned["a"]["height"] > 200
    assert positioned["b"]["y"] >= positioned["a"]["y"] + positioned["a"]["height"] + 28
    assert lint_visual_model(ET.fromstring(xml))["valid"]


def test_a_real_unused_role_is_retained_as_a_small_band():
    nodes = [("s", "startEvent", ""), ("a", "userTask", "Verificare"), ("e", "endEvent", "")]
    xml = apply_enterprise_layout(semantic(nodes, [("s", "a"), ("a", "e")], [("role", "Acquisti", ["s", "a", "e"]), ("unused", "Amministrazione", [])]))
    assert shapes(xml)["unused"]["height"] <= 64
    assert ET.fromstring(xml).find(".//b:lane[@id='unused']", NS) is not None
