"""L3 reachability checks inspect the actual canvas XML, not only its plan."""

from pathlib import Path

from backend.bpmn.xml_behavior import analyze_canvas_xml_behavior
from backend.workspace_services.bpmn_canvas_validation import validate_canvas_against_process

XML = (Path(__file__).resolve().parents[1] / "fixtures" / "omg_valid_minimal.bpmn").read_text(
    encoding="utf-8",
)


def test_complete_simple_process_has_no_reachability_issues():
    report = analyze_canvas_xml_behavior(XML)
    assert report["valid"] is True
    assert report["processes_analyzed"] == 1
    assert report["behavioral_scope"] == "top_level_reachability_only"


def test_empty_process_does_not_claim_soundness_proof():
    xml = ('<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL" '
           'id="D"><process id="P"/></definitions>')
    report = analyze_canvas_xml_behavior(xml)
    assert report["behavioral_scope"] == "no_flow_nodes_analyzed"
    assert any("soundness non determinabile" in warning for warning in report["warnings"])


def test_disconnected_task_is_reported_from_actual_xml():
    xml = XML.replace('<bpmn:endEvent id="End"', '<bpmn:task id="Orphan" name="Forgotten" />\n    '
                      '<bpmn:endEvent id="End"')
    report = validate_canvas_against_process(xml=xml)
    assert report["behavioral_valid"] is False
    assert any("Orphan non raggiungibile" in issue for issue in report["issues"])
    assert any("Orphan senza percorso" in issue for issue in report["issues"])


def test_flow_cannot_cross_process_boundary():
    xml = XML.replace('targetRef="Review"', 'targetRef="Outside"')
    report = analyze_canvas_xml_behavior(xml)
    assert any("punta fuori dal grafo" in issue for issue in report["issues"])


def test_parallel_gateway_report_does_not_claim_deadlock_freedom():
    xml = XML.replace('<bpmn:task id="Review"', '<bpmn:parallelGateway id="Fork" />\n    '
                      '<bpmn:task id="Review"')
    report = analyze_canvas_xml_behavior(xml)
    assert any("non prova l'assenza di deadlock" in warning for warning in report["warnings"])


def test_behavior_tool_keeps_l2_and_l3_results_separate(monkeypatch):
    from backend.toolsets import bpmn as canvas_tools

    xml = XML.replace('<bpmn:endEvent id="End"', '<bpmn:task id="Orphan" />\n    '
                      '<bpmn:endEvent id="End"')
    monkeypatch.setattr(canvas_tools, "_state_or_saved_canvas_xml", lambda *_args: (xml, "live_canvas"))
    monkeypatch.setattr(canvas_tools, "_review_or_state_semantic_context",
                        lambda *_args: (None, None, None))
    result = canvas_tools.manage_canvas_validation.func(
        bpmn_model_id="model-1", operation="behavior_validation", state={},
        objective="Check paths", tool_call_id="call-1",
    )
    report = result.update["validation_report"]
    assert report["xml_valid"] is True
    assert report["behavioral_valid"] is False
    assert report["semantic_valid"] is None
