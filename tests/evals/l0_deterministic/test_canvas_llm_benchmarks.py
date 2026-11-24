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


def test_ambiguous_request_is_correct_only_without_an_edit():
    case = next(item for item in cycle.CASES if item.operation == "none")
    asked = cycle.run_case(_ScriptedModel([]), case, "map")
    assert asked["correct"] is True and asked["applied"] is None
    guessed = cycle.run_case(
        _ScriptedModel([{"name": "update_element", "args": {"element_id": "Task_0_A", "name": "Verifica completa"}}]),
        case, "map",
    )
    assert guessed["correct"] is False


def _rate_limit(message: str):
    import httpx
    import openai

    response = httpx.Response(429, request=httpx.Request("POST", "https://example.invalid"))
    return openai.RateLimitError(message, response=response, body=None)


def test_patient_client_waits_what_the_provider_asks_and_counts_it(monkeypatch):
    from langchain_openai import ChatOpenAI

    from scripts import live_llm_support as support

    attempts = []

    def flaky(self, *args, **kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise _rate_limit("Rate limit reached on tokens per minute (TPM). Please try again in 1.5s.")
        return "ok"

    slept = []
    monkeypatch.setattr(ChatOpenAI, "_generate", flaky)
    monkeypatch.setattr(support, "sleep", slept.append)
    monkeypatch.setitem(support.RETRY_STATS, "retries", 0)
    monkeypatch.setitem(support.RETRY_STATS, "waited_s", 0.0)
    client = support.build_client("m", "https://example.invalid/v1", "k")
    assert client._generate([]) == "ok"
    assert slept == [2.0] and support.RETRY_STATS == {"retries": 1, "waited_s": 2.0}


def test_daily_caps_are_not_waited_out(monkeypatch):
    from langchain_openai import ChatOpenAI

    from scripts import live_llm_support as support

    def capped(self, *args, **kwargs):
        raise _rate_limit("Rate limit reached on tokens per day (TPD). Please try again in 14m3s.")

    monkeypatch.setattr(ChatOpenAI, "_generate", capped)
    monkeypatch.setattr(support, "sleep", lambda _s: pytest.fail("must not wait"))
    with pytest.raises(Exception, match="per day"):
        support.build_client("m", None, "k")._generate([])
    assert support.retry_wait_seconds(_rate_limit("try again in 2m3.5s")) == pytest.approx(123.5)
    assert support.retry_wait_seconds(_rate_limit("try again in 250ms")) == pytest.approx(0.25)


def test_wilson_interval_is_honest_on_small_samples():
    from scripts.live_llm_support import wilson_interval

    assert wilson_interval(0, 0) is None
    low, high = wilson_interval(3, 3)
    assert high == 1.0 and low < 0.5


def test_runtime_benchmark_refuses_development_database(monkeypatch):
    from scripts import benchmark_canvas_runtime as runtime

    monkeypatch.setenv("WORKSPACE_DATABASE_URL", "postgresql+psycopg://u:p@127.0.0.1:55300/workspace")
    with pytest.raises(SystemExit):
        runtime._assert_test_database()
    monkeypatch.setenv("WORKSPACE_DATABASE_URL", "postgresql+psycopg://u:p@127.0.0.1:55375/workspace")
    runtime._assert_test_database()


def test_runtime_reduction_is_paired_and_skips_failed_runs():
    from scripts.benchmark_canvas_runtime import summarize

    def row(fixture, representation, tokens, **extra):
        return {"fixture": fixture, "operation": "update_element", "repeat": 0,
                "representation": representation, "calls": 1, "usage_reported_calls": 1,
                "input_tokens": tokens, "output_tokens": 0, "correct": True,
                "integrity_violations": 0, "latency_ms": 1.0, "retries": 0, **extra}

    report = summarize([
        row("a", "xml", 1000), row("a", "map", 600),
        row("b", "xml", 2000), row("b", "map", 1000),
        row("c", "xml", 3000), row("c", "map", 0, error_type="RateLimitError"),
    ])
    assert report["paired_cases"] == 2
    assert report["paired_token_reduction_median"] == pytest.approx(0.45)
    assert report["map"]["errors"] == 1


def test_prompt_budget_separates_fixed_prompt_from_canvas():
    from scripts.benchmark_canvas_prompt_budget import report

    result = report()
    fixed = ("procedural_memory", "subgraph_contract", "tool_schemas", "conversation")
    for xml_row, map_row in zip(result["rows"][0::2], result["rows"][1::2], strict=True):
        assert xml_row["fixture"] == map_row["fixture"]
        # Only the scope prompt carries the canvas: everything else is identical.
        assert all(xml_row[key] == map_row[key] for key in fixed)
        assert map_row["scope_prompt"] < xml_row["scope_prompt"]
    assert 0 < result["summary"]["first_call_reduction_median"] < 1
