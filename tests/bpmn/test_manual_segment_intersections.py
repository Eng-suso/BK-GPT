"""Manual DI can contain diagonal associations; only actual hits are violations."""
import pytest

from backend.bpmn.canvas_layout.geometry import Box
from backend.bpmn.canvas_layout.router import segment_hits_box


@pytest.mark.parametrize("a,b,hit", [
    ((0, 0), (100, 100), True),
    ((100, 100), (0, 0), True),
    ((0, 0), (100, 20), False),
    ((0, 80), (80, 0), False),  # touches one corner only
    ((45, 45), (46, 46), True),
    ((0, 0), (40, 40), False),  # ends on the boundary
    ((40, 40), (60, 60), True),
    ((0, 50), (100, 50), True),
    ((50, 0), (50, 100), True),
    ((0, 40), (100, 40), False),
    ((50, 50), (50, 50), False),
])
def test_actual_segment_interior_intersection(a, b, hit):
    assert segment_hits_box(a, b, Box(40, 40, 20, 20)) is hit


def test_manual_diagonal_association_checks_actual_obstacles_without_rewriting_xml():
    from backend.workspace_services.bpmn_canvas_edit import validate_bpmn_layout
    from backend.bpmn.canvas_layout.policy import BPMN, BPMNDI, DC, DI
    tasks = [("Source", 0, 0)] + [(f"Other{i}", i * 160, 400) for i in range(7)]
    shapes = "".join(f'<bd:BPMNShape id="{id}_di" bpmnElement="{id}"><dc:Bounds x="{x}" y="{y}" width="80" height="50"/></bd:BPMNShape>' for id, x, y in tasks)
    xml = f'<b:definitions xmlns:b="{BPMN}" xmlns:bd="{BPMNDI}" xmlns:dc="{DC}" xmlns:di="{DI}" targetNamespace="urn:manual"><b:process id="Process">' + "".join(f'<b:task id="{id}"/>' for id, _, _ in tasks) + '<b:textAnnotation id="Note"><b:text>Controllo</b:text></b:textAnnotation><b:association id="Association" sourceRef="Source" targetRef="Note"/></b:process><bd:BPMNDiagram id="Diagram"><bd:BPMNPlane id="Plane" bpmnElement="Process">' + shapes + '<bd:BPMNShape id="Note_di" bpmnElement="Note"><dc:Bounds x="500" y="150" width="80" height="50"/></bd:BPMNShape><bd:BPMNEdge id="Association_di" bpmnElement="Association"><di:waypoint x="80" y="25"/><di:waypoint x="500" y="175"/></bd:BPMNEdge></bd:BPMNPlane></bd:BPMNDiagram></b:definitions>'
    report = validate_bpmn_layout(xml)
    assert report["valid"], report
    # Crossing a genuine obstacle is still a violation; this is no blanket bypass.
    blocked = xml.replace('x="480" y="400"', 'x="250" y="70"')
    report = validate_bpmn_layout(blocked)
    assert not report["valid"]
    assert [issue for issue in report["issues"] if "Il flusso Association attraversa" in issue] == ["Il flusso Association attraversa Other3."]
