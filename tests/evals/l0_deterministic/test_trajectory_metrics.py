"""Le metriche di traiettoria dicono il vero, su percorsi scritti a mano."""

from __future__ import annotations

from langchain_core.messages import AIMessage, ToolMessage

from tests.evals.trajectory_metrics import (
    CallRule,
    ExpectedTrajectory,
    ToolCall,
    aggregate_trajectories,
    score_trajectory,
    tool_calls,
)

PROVENANCE = ExpectedTrajectory(
    id="da_dove_viene",
    agent="process",
    request="Da dove viene che la soglia e' 5.000 euro?",
    rule="-",
    rule_source="-",
    must_call=[CallRule("manage_process_evidence", {"operation": ["provenance"]})],
    must_not_call=[CallRule("synthesize_process_evidence")],
    max_tool_calls=3,
)


def _ai(*calls: tuple[str, dict]) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": f"c{index}"} for index, (name, args) in enumerate(calls)],
    )


def test_the_calls_come_out_of_the_messages_in_order():
    messages = [
        _ai(("get_process_evidence_brief", {})),
        ToolMessage(content="ok", tool_call_id="c0"),
        _ai(("manage_process_evidence", {"operation": "provenance"})),
        AIMessage(content="Lo dicono Laura e Chiara."),
    ]

    assert [call.name for call in tool_calls(messages)] == ["get_process_evidence_brief", "manage_process_evidence"]


def test_serialized_messages_count_too():
    messages = [{"type": "ai", "tool_calls": [{"name": "manage_process_evidence", "args": {"operation": "ledger"}}]}]

    assert tool_calls(messages) == [ToolCall("manage_process_evidence", {"operation": "ledger"})]


def test_reading_the_provenance_is_the_right_path():
    result = score_trajectory(PROVENANCE, [ToolCall("manage_process_evidence", {"operation": "Provenance "})])

    assert result.correct
    assert not result.over_budget


def test_the_right_tool_with_the_wrong_operation_is_not_enough():
    """`manage_process_evidence` fa anche list e save: conta l'operazione."""
    result = score_trajectory(PROVENANCE, [ToolCall("manage_process_evidence", {"operation": "list"})])

    assert result.missing == ["manage_process_evidence(operation in ['provenance'])"]


def test_answering_with_a_new_synthesis_is_forbidden_even_after_the_provenance():
    result = score_trajectory(
        PROVENANCE,
        [
            ToolCall("manage_process_evidence", {"operation": "provenance"}),
            ToolCall("synthesize_process_evidence", {}),
        ],
    )

    assert result.forbidden == ["synthesize_process_evidence"]
    assert not result.correct


def test_the_same_call_twice_is_redundant_and_the_budget_counts_every_call():
    call = ToolCall("manage_process_evidence", {"operation": "provenance"})

    result = score_trajectory(PROVENANCE, [call, call, call, call])

    assert result.redundant == 3
    assert result.over_budget


def test_the_aggregate_over_tasks():
    right = score_trajectory(PROVENANCE, [ToolCall("manage_process_evidence", {"operation": "provenance"})])
    wrong = score_trajectory(PROVENANCE, [ToolCall("synthesize_process_evidence", {})])

    assert aggregate_trajectories([right, wrong]) == {
        "tool_selection_accuracy": 0.5,
        "forbidden_rate": 0.5,
        "redundant_call_rate": 0.0,
        "over_budget_rate": 0.0,
    }
