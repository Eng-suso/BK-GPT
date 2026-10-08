"""Product geometry comes from semantics, never agent DI or XML child order."""
import xml.etree.ElementTree as ET
from itertools import pairwise

import pytest

from backend.bpmn.canvas_layout import apply_enterprise_layout, lint_visual_model
from backend.bpmn.canvas_layout.policy import BPMN, BPMNDI, DC, DI

NS = {"b": BPMN, "bd": BPMNDI, "dc": DC, "di": DI}


def semantic(nodes, flows, lanes=()):
    lane_set = '<b:laneSet id="roles">' + "".join(f'<b:lane id="{id}" name="{name}">' + "".join(f'<b:flowNodeRef>{node}</b:flowNodeRef>' for node in members) + '</b:lane>' for id, name, members in lanes) + '</b:laneSet>' if lanes else ""
    return f'<b:definitions xmlns:b="{BPMN}" id="def"><b:process id="process" name="Acquisti indiretti">{lane_set}' + "".join(f'<b:{type} id="{id}" name="{name}"/>' for id, type, name in nodes) + "".join(f'<b:sequenceFlow id="f{i}" sourceRef="{source}" targetRef="{target}"/>' for i, (source, target) in enumerate(flows)) + '</b:process></b:definitions>'


def shapes(xml):
    root = ET.fromstring(xml)
    return {s.get("bpmnElement"): {key: float(s.find("dc:Bounds", NS).get(key)) for key in ("x", "y", "width", "height")} for s in root.findall(".//bd:BPMNShape", NS)}


LINEAR = [("start", "startEvent", ""), ("verify", "userTask", "Verificare dati"), ("record", "userTask", "Registrare esito"), ("end", "endEvent", "")]
LINEAR_FLOWS = [("start", "verify"), ("verify", "record"), ("record", "end")]


def test_roles_are_lanes_inside_the_named_process_boundary_and_compact_width():
    xml = apply_enterprise_layout(semantic(LINEAR, LINEAR_FLOWS, [("buying", "Acquisti", ["verify", "record"])]))
    root, positioned = ET.fromstring(xml), shapes(xml)
    pool = root.find(".//b:participant", NS)
    assert pool.get("name") == "Acquisti indiretti"
    assert pool.get("processRef") == "process"
    assert root.find(".//b:lane", NS).get("name") == "Acquisti"
    assert len(root.findall(".//b:participant", NS)) == 1
    assert positioned[pool.get("id")]["width"] < 1000
    assert positioned["buying"]["height"] < 300
    assert [positioned[id]["x"] for id, _, _ in LINEAR] == sorted(positioned[id]["x"] for id, _, _ in LINEAR)


def test_geometry_is_idempotent_and_discards_arbitrary_agent_di():
    xml = semantic(LINEAR, LINEAR_FLOWS)
    expected = apply_enterprise_layout(xml)
    injected = xml.replace('</b:definitions>', f'<bd:BPMNDiagram xmlns:bd="{BPMNDI}" xmlns:dc="{DC}" id="fake"><bd:BPMNPlane id="fakeplane" bpmnElement="process"><bd:BPMNShape id="fake_shape" bpmnElement="verify"><dc:Bounds x="-9999" y="7000" width="100000" height="2"/></bd:BPMNShape></bd:BPMNPlane></bd:BPMNDiagram></b:definitions>')
    assert apply_enterprise_layout(injected) == expected
    assert apply_enterprise_layout(expected) == expected


def test_xml_order_does_not_choose_visual_order():
    expected = shapes(apply_enterprise_layout(semantic(LINEAR, LINEAR_FLOWS)))
    actual = shapes(apply_enterprise_layout(semantic(list(reversed(LINEAR)), LINEAR_FLOWS)))
    assert actual == expected


def test_handoffs_change_lane_without_restarting_x_or_inventing_owners():
    lanes = [("finance", "Amministrazione", ["record"]), ("buying", "Acquisti", ["verify"])]
    xml = apply_enterprise_layout(semantic(LINEAR, LINEAR_FLOWS, lanes))
    positioned = shapes(xml)
    assert positioned["buying"]["y"] < positioned["finance"]["y"]
    assert positioned["record"]["x"] > positioned["verify"]["x"]
    root = ET.fromstring(xml)
    assert {lane.get("id"): [ref.text for ref in lane.findall("b:flowNodeRef", NS)] for lane in root.findall(".//b:lane", NS)} == {id: members for id, _, members in lanes}


def test_split_branches_share_rank_and_are_symmetric_before_join():
    nodes = [("s", "startEvent", ""), ("split", "parallelGateway", ""), ("a", "userTask", "Controllare"), ("b", "userTask", "Confrontare"), ("join", "parallelGateway", ""), ("e", "endEvent", "")]
    flows = [("s", "split"), ("split", "a"), ("split", "b"), ("a", "join"), ("b", "join"), ("join", "e")]
    xml = apply_enterprise_layout(semantic(nodes, flows, [("role", "Acquisti", [id for id, _, _ in nodes])]))
    positioned = shapes(xml)
    assert positioned["a"]["x"] == positioned["b"]["x"]
    center = lambda id: positioned[id]["y"] + positioned[id]["height"] / 2
    assert center("split") == center("join") == (center("a") + center("b")) / 2
    assert positioned["join"]["x"] > positioned["a"]["x"]
    assert lint_visual_model(ET.fromstring(xml))["valid"]


def test_feedback_uses_orthogonal_routes_without_crossing_tasks():
    flows = LINEAR_FLOWS + [("record", "verify")]
    xml = apply_enterprise_layout(semantic(LINEAR, flows))
    root = ET.fromstring(xml)
    report = lint_visual_model(root)
    assert report["valid"], report
    assert len(root.findall(".//bd:BPMNEdge", NS)) == 4
    for edge in root.findall(".//bd:BPMNEdge", NS):
        points = [(float(e.get("x")), float(e.get("y"))) for e in edge.findall("di:waypoint", NS)]
        assert all(a[0] == b[0] or a[1] == b[1] for a, b in pairwise(points))


@pytest.mark.parametrize("mutation", ["duplicate_id", "foreign_flow", "unknown_owner", "two_owners"])
def test_invalid_semantics_are_rejected_before_di_generation(mutation):
    xml = semantic(LINEAR, LINEAR_FLOWS, [("role", "Acquisti", ["verify"])] )
    if mutation == "duplicate_id":
        xml = xml.replace('id="record"', 'id="verify"')
    elif mutation == "foreign_flow":
        xml = xml.replace('targetRef="record"', 'targetRef="unknown"')
    elif mutation == "unknown_owner":
        xml = xml.replace('<b:flowNodeRef>verify</b:flowNodeRef>', '<b:flowNodeRef>unknown</b:flowNodeRef>')
    else:
        xml = xml.replace('</b:laneSet>', '<b:lane id="other" name="Operations"><b:flowNodeRef>verify</b:flowNodeRef></b:lane></b:laneSet>')
    with pytest.raises(ValueError):
        apply_enterprise_layout(xml)
