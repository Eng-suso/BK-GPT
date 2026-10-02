from backend.bpmn.models import BPMNFlowNode, BPMNSemanticModel, BPMNSequenceFlow
from backend.bpmn.soundness import analyze_control_flow


def _model(nodes: list[BPMNFlowNode], flows: list[tuple[str, str]]) -> BPMNSemanticModel:
    return BPMNSemanticModel(
        id="P",
        name="P",
        flowNodes=nodes,
        sequenceFlows=[
            BPMNSequenceFlow(id=f"F_{s}_{t}", sourceRef=s, targetRef=t) for s, t in flows
        ],
    )


def _n(node_id: str, node_type: str = "task", **kw) -> BPMNFlowNode:
    return BPMNFlowNode(id=node_id, type=node_type, name=node_id, **kw)


def test_linear_process_is_sound():
    model = _model(
        [_n("s", "startEvent"), _n("a"), _n("e", "endEvent")],
        [("s", "a"), ("a", "e")],
    )
    report = analyze_control_flow(model)
    assert report.is_sound
    assert report.errors == []


def test_unreachable_and_dead_end_nodes_are_errors():
    model = _model(
        [_n("s", "startEvent"), _n("a"), _n("orphan"), _n("trap"), _n("e", "endEvent")],
        [("s", "a"), ("a", "e"), ("trap", "trap")],
    )
    report = analyze_control_flow(model)
    codes = {issue.code for issue in report.errors}
    assert "unreachable_node" in codes  # orphan, trap
    assert "dead_end_node" in codes  # trap loops on itself, never reaches e
    assert not report.is_sound


def test_task_with_two_outgoing_is_an_implicit_split_error():
    model = _model(
        [_n("s", "startEvent"), _n("a"), _n("b"), _n("c"), _n("e", "endEvent")],
        [("s", "a"), ("a", "b"), ("a", "c"), ("b", "e"), ("c", "e")],
    )
    report = analyze_control_flow(model)
    split = next(i for i in report.errors if i.code == "implicit_parallel_split")
    assert split.node_id == "a"
    # 'e' has two incoming but is an end event -> not flagged
    assert not any(i.node_id == "e" for i in report.warnings)


def test_parallel_gateway_split_and_join_is_sound():
    model = _model(
        [
            _n("s", "startEvent"),
            _n("split", "parallelGateway"),
            _n("a"),
            _n("b"),
            _n("join", "parallelGateway"),
            _n("e", "endEvent"),
        ],
        [
            ("s", "split"),
            ("split", "a"),
            ("split", "b"),
            ("a", "join"),
            ("b", "join"),
            ("join", "e"),
        ],
    )
    report = analyze_control_flow(model)
    assert report.is_sound


def test_parallel_split_without_join_warns():
    model = _model(
        [
            _n("s", "startEvent"),
            _n("split", "parallelGateway"),
            _n("a"),
            _n("b"),
            _n("e1", "endEvent"),
            _n("e2", "endEvent"),
        ],
        [("s", "split"), ("split", "a"), ("split", "b"), ("a", "e1"), ("b", "e2")],
    )
    report = analyze_control_flow(model)
    assert any(i.code == "parallel_split_without_join" for i in report.warnings)
    assert report.is_sound  # heuristic warning, not an error


def test_gateway_that_both_joins_and_splits_is_an_error():
    model = _model(
        [
            _n("s", "startEvent"),
            _n("a"),
            _n("b"),
            _n("g", "exclusiveGateway"),
            _n("x"),
            _n("y"),
            _n("e", "endEvent"),
        ],
        [
            ("s", "a"),
            ("s", "b"),  # implicit split on start, separate issue
            ("a", "g"),
            ("b", "g"),
            ("g", "x"),
            ("g", "y"),
            ("x", "e"),
            ("y", "e"),
        ],
    )
    report = analyze_control_flow(model)
    assert any(i.code == "gateway_splits_and_joins" and i.node_id == "g" for i in report.errors)


def test_nested_boundary_events_are_not_false_unreachable_regardless_of_order():
    # 'bnd2' (listed first) is attached to 'handler1', which is only reachable
    # through 'bnd1' (listed after it). A single-pass propagation would flag
    # handler2's subtree as unreachable.
    model = _model(
        [
            _n("s", "startEvent"),
            _n("bnd2", "boundaryEvent", attachedToRef="handler1"),
            _n("wait"),
            _n("bnd1", "boundaryEvent", attachedToRef="wait"),
            _n("handler1"),
            _n("handler2"),
            _n("e", "endEvent"),
            _n("e1", "endEvent"),
            _n("e2", "endEvent"),
        ],
        [
            ("s", "wait"),
            ("wait", "e"),
            ("bnd1", "handler1"),
            ("handler1", "e1"),
            ("bnd2", "handler2"),
            ("handler2", "e2"),
        ],
    )
    report = analyze_control_flow(model)
    assert {"handler1", "handler2", "bnd1", "bnd2"} <= report.reachable_node_ids
    assert not any(i.code == "unreachable_node" for i in report.errors)


def test_boundary_event_handler_reachability():
    model = _model(
        [
            _n("s", "startEvent"),
            _n("wait"),
            _n("bnd", "boundaryEvent", attachedToRef="wait"),
            _n("handler"),
            _n("e", "endEvent"),
            _n("he", "endEvent"),
        ],
        [("s", "wait"), ("wait", "e"), ("bnd", "handler"), ("handler", "he")],
    )
    report = analyze_control_flow(model)
    assert "handler" in report.reachable_node_ids
    assert report.is_sound
