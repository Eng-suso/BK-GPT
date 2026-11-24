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
    assert report["behavioral_scope"] == "top_level_reachability_and_tokens"


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


def _process(body: str) -> str:
    return ('<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
            'id="D" targetNamespace="urn:delir:test"><bpmn:process id="P">'
            f'{body}</bpmn:process></bpmn:definitions>')


def _flows(*pairs: str) -> str:
    return "".join(
        f'<bpmn:sequenceFlow id="F{index}" sourceRef="{pair.split(">")[0]}" targetRef="{pair.split(">")[1]}"/>'
        for index, pair in enumerate(pairs)
    )


def _codes(report: dict) -> set[str]:
    return {finding["code"] for finding in report["findings"]}


def test_exclusive_split_into_parallel_join_is_a_deadlock():
    xml = _process(
        '<bpmn:startEvent id="S"/><bpmn:exclusiveGateway id="X" name="Importo alto?"/>'
        '<bpmn:task id="A" name="Approva"/><bpmn:task id="B" name="Archivia"/>'
        '<bpmn:parallelGateway id="J" name="Attendi entrambi"/><bpmn:endEvent id="E"/>'
        + _flows("S>X", "X>A", "X>B", "A>J", "B>J", "J>E")
    )
    report = analyze_canvas_xml_behavior(xml)
    assert report["valid"] is False
    assert _codes(report) == {"deadlock"}
    deadlock = report["findings"][0]
    assert deadlock["element_id"] == "J" and deadlock["element_name"] == "Attendi entrambi"
    assert report["behavioral_scope"] == "top_level_reachability_and_tokens"


def test_parallel_split_into_exclusive_merge_lacks_synchronization():
    xml = _process(
        '<bpmn:startEvent id="S"/><bpmn:parallelGateway id="Fork"/>'
        '<bpmn:task id="A"/><bpmn:task id="B"/><bpmn:exclusiveGateway id="M"/>'
        '<bpmn:task id="C" name="Invia esito"/><bpmn:endEvent id="E"/>'
        + _flows("S>Fork", "Fork>A", "Fork>B", "A>M", "B>M", "M>C", "C>E")
    )
    report = analyze_canvas_xml_behavior(xml)
    assert "lack_of_synchronization" in _codes(report)
    assert "deadlock" not in _codes(report)


def test_balanced_parallel_block_and_exclusive_loop_are_accepted():
    xml = _process(
        '<bpmn:startEvent id="S"/><bpmn:exclusiveGateway id="Merge"/><bpmn:parallelGateway id="Fork"/>'
        '<bpmn:task id="A"/><bpmn:task id="B"/><bpmn:parallelGateway id="Join"/>'
        '<bpmn:task id="Check"/><bpmn:exclusiveGateway id="Ok"/><bpmn:endEvent id="E"/>'
        + _flows("S>Merge", "Merge>Fork", "Fork>A", "Fork>B", "A>Join", "B>Join", "Join>Check",
                 "Check>Ok", "Ok>Merge", "Ok>E")
    )
    report = analyze_canvas_xml_behavior(xml)
    assert report["valid"] is True, report["issues"]
    assert report["coverage"]["token_game_processes"] == 1
    assert not any("deadlock" in warning for warning in report["warnings"])


def test_loop_back_into_a_parallel_gateway_is_a_join_that_waits_forever():
    # A parallel gateway with two incoming flows synchronizes them (OMG BPMN
    # 2.0.2, 13.4.2): the loop back can never arrive together with the start.
    xml = _process(
        '<bpmn:startEvent id="S"/><bpmn:parallelGateway id="Fork"/><bpmn:task id="A"/>'
        '<bpmn:exclusiveGateway id="Ok"/><bpmn:endEvent id="E"/>'
        + _flows("S>Fork", "Fork>A", "A>Ok", "Ok>Fork", "Ok>E")
    )
    assert "deadlock" in _codes(analyze_canvas_xml_behavior(xml))


def test_terminate_end_event_stops_parallel_branches():
    xml = _process(
        '<bpmn:startEvent id="S"/><bpmn:parallelGateway id="Fork"/>'
        '<bpmn:task id="A"/><bpmn:task id="B"/>'
        '<bpmn:endEvent id="Stop"><bpmn:terminateEventDefinition/></bpmn:endEvent>'
        '<bpmn:endEvent id="E"/>'
        + _flows("S>Fork", "Fork>A", "Fork>B", "A>Stop", "B>E")
    )
    assert analyze_canvas_xml_behavior(xml)["valid"] is True


def test_interrupting_boundary_event_is_an_alternative_exit():
    xml = _process(
        '<bpmn:startEvent id="S"/><bpmn:parallelGateway id="Fork"/>'
        '<bpmn:task id="A"/><bpmn:task id="B"/>'
        '<bpmn:boundaryEvent id="Timeout" attachedToRef="A"><bpmn:timerEventDefinition/></bpmn:boundaryEvent>'
        '<bpmn:parallelGateway id="Join"/><bpmn:endEvent id="E"/><bpmn:endEvent id="Late"/>'
        + _flows("S>Fork", "Fork>A", "Fork>B", "A>Join", "B>Join", "Join>E", "Timeout>Late")
    )
    report = analyze_canvas_xml_behavior(xml)
    # The timer path leaves the join waiting for A: a real deadlock in BPMN.
    assert "deadlock" in _codes(report)


def test_inclusive_gateway_is_declared_out_of_scope_not_called_sound():
    xml = _process(
        '<bpmn:startEvent id="S"/><bpmn:inclusiveGateway id="Or"/><bpmn:task id="A"/>'
        '<bpmn:task id="B"/><bpmn:inclusiveGateway id="OrJoin"/><bpmn:endEvent id="E"/>'
        + _flows("S>Or", "Or>A", "Or>B", "A>OrJoin", "B>OrJoin", "OrJoin>E")
    )
    report = analyze_canvas_xml_behavior(xml)
    assert report["valid"] is True
    assert report["behavioral_scope"] == "top_level_reachability_only"
    assert any("non prova l'assenza di deadlock" in warning and "inclusiveGateway" in warning
               for warning in report["warnings"])


def test_token_budget_exhaustion_is_reported_not_treated_as_proof():
    branches = "".join(f'<bpmn:task id="T{i}"/>' for i in range(14))
    xml = _process(
        '<bpmn:startEvent id="S"/><bpmn:parallelGateway id="Fork"/>' + branches
        + '<bpmn:parallelGateway id="Join"/><bpmn:endEvent id="E"/>'
        + _flows("S>Fork", *(f"Fork>T{i}" for i in range(14)), *(f"T{i}>Join" for i in range(14)), "Join>E")
    )
    report = analyze_canvas_xml_behavior(xml, token_budget=100)
    assert report["valid"] is True
    assert report["coverage"]["token_game_skipped"] == 1
    assert any("interrotta oltre 100 stati" in warning for warning in report["warnings"])
