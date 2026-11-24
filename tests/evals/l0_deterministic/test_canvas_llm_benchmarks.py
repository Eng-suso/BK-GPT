"""Deterministic checks of the live canvas benchmarks: scoring, not the model."""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage

from backend.bpmn.compact_representation import semantic_tree
from scripts import benchmark_canvas_edit_cycle as cycle
from scripts import benchmark_canvas_source_fidelity as fidelity


class _ScriptedModel:
    """Replays tool calls; reports usage like an OpenAI-compatible provider."""

    def __init__(self, *turns: list[dict]) -> None:
        self.turns = list(turns)

    def bind_tools(self, _tools):
        return self

    def invoke(self, _messages):
        calls = self.turns.pop(0)
        return AIMessage(content="", tool_calls=[{**call, "id": f"c{i}"} for i, call in enumerate(calls)],
                         usage_metadata={"input_tokens": 100, "output_tokens": 10, "total_tokens": 110})


def test_expected_edit_is_correct_in_one_call():
    case = cycle.CASES[0]
    model = _ScriptedModel([{"name": "update_element", "args": {"element_id": "Review", "name": "Check request"}}])
    row = cycle.run_case(model, case, "map")
    assert row["correct"] is True and row["calls"] == 1 and row["integrity_ok"] is True
    assert row["input_tokens"] == 100 and row["output_tokens"] == 10


def test_unknown_id_goes_back_to_the_model_and_costs_a_call():
    case = cycle.CASES[1]
    model = _ScriptedModel(
        [{"name": "delete_element", "args": {"element_id": "Invented"}}],
        [{"name": "delete_element", "args": {"element_id": "Director_Sign"}}],
    )
    row = cycle.run_case(model, case, "xml")
    assert row["calls"] == 2 and row["correct"] is True


def test_editing_the_wrong_element_is_not_correct():
    case = cycle.CASES[0]
    model = _ScriptedModel([{"name": "update_element", "args": {"element_id": "End", "name": "Check request"}}])
    row = cycle.run_case(model, case, "xml")
    assert row["integrity_ok"] is True and row["correct"] is False
    assert semantic_tree(cycle.apply_operation(cycle._fixture_xml(case), "update_element", "End",
                                               "Check request")[0]) != cycle.expected_semantics(case)


def test_cycle_summary_separates_provider_errors_and_reduction():
    rows = [
        {"representation": "xml", "calls": 1, "usage_reported_calls": 1, "input_tokens": 1000,
         "output_tokens": 20, "correct": True, "integrity_ok": True, "latency_ms": 10},
        {"representation": "map", "calls": 1, "usage_reported_calls": 1, "input_tokens": 200,
         "output_tokens": 20, "correct": True, "integrity_ok": True, "latency_ms": 10},
        {"representation": "map", "error_type": "RateLimitError", "latency_ms": 5},
    ]
    report = cycle.summarize(rows)
    assert report["map"]["provider_errors"] == 1 and report["map"]["correct"] == 1
    assert report["token_reduction_median"] == pytest.approx(1 - 220 / 1020, abs=1e-4)


@pytest.mark.parametrize("case", fidelity.CASES, ids=lambda case: case.name)
@pytest.mark.parametrize("representation", fidelity.REPRESENTATIONS)
def test_every_representation_carries_the_planted_discrepancies(case, representation):
    body = fidelity.represent(fidelity.build_model(case), representation)
    assert case.invent in body
    assert case.missing_label not in body


def test_fidelity_scoring_counts_hallucinated_findings():
    case = fidelity.CASES[0]
    answer = fidelity.parse_answer(
        '```json\n{"missing_from_model": ["Verifica dell\'autorizzazione", "Pagamento"],'
        ' "unsupported_in_model": ["Invia sondaggio di soddisfazione"]}\n```'
    )
    assert fidelity.score(answer, case) == {
        "found_missing": True, "found_unsupported": True, "false_positives": 1,
    }
    with pytest.raises(ValueError):
        fidelity.parse_answer('{"missing_from_model": []}')
