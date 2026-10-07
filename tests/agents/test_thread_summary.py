"""Il riassunto del thread: parte quando serve, e un suo guasto non fa cadere il turno.

Prima `summarize_node` chiamava il modello senza rete: un timeout del
riassunto - manutenzione, non la risposta - faceva fallire il turno del
consulente. E scattava solo a numero di messaggi: pochi messaggi enormi (il
risultato di un tool) non lo attivavano mai.
"""

from __future__ import annotations

import logging

import httpx
import openai
import pytest
from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, ToolMessage

from backend.agent import (
    FALLBACK_TOTAL_CHARS,
    SUMMARY_KEEP_RECENT_MESSAGES,
    SUMMARY_TRIGGER_MESSAGE_COUNT,
    summarize_history,
)
from backend.llm import OperationNotOpen
from backend.services import degradation_counters


def _thread(n: int, text: str = "turno") -> list:
    messages = []
    for i in range(n):
        cls = HumanMessage if i % 2 == 0 else AIMessage
        messages.append(cls(content=f"{text} {i}", id=f"m{i}"))
    return messages


def test_a_short_thread_is_left_alone():
    calls = []

    out = summarize_history({"messages": _thread(4)}, lambda s, m: calls.append(m) or "x")

    assert out == {}
    assert calls == []


def test_a_long_thread_is_summarized_and_trimmed():
    messages = _thread(SUMMARY_TRIGGER_MESSAGE_COUNT + 2)

    out = summarize_history({"messages": messages}, lambda existing, old: "sintesi")

    assert out["running_summary"] == "sintesi"
    removed = [op.id for op in out["messages"] if isinstance(op, RemoveMessage)]
    assert removed == [m.id for m in messages[: len(messages) - SUMMARY_KEEP_RECENT_MESSAGES]]


def _with_huge(messages: list, indexes: range) -> list:
    huge = "parola " * 30_000
    for i in indexes:
        messages[i] = type(messages[i])(content=huge, id=messages[i].id)
    return messages


def test_a_few_huge_messages_trigger_the_summary_too():
    messages = _with_huge(_thread(SUMMARY_KEEP_RECENT_MESSAGES + 2), range(2))

    out = summarize_history({"messages": messages}, lambda existing, old: "sintesi")

    assert len(messages) <= SUMMARY_TRIGGER_MESSAGE_COUNT
    assert out["running_summary"] == "sintesi"


def test_a_huge_recent_tail_does_not_trigger_the_summary():
    # Gli ultimi messaggi restano interi comunque: contarli faceva ripartire il
    # riassunto a ogni turno, una chiamata al modello per comprimere due righe.
    messages = _with_huge(
        _thread(SUMMARY_KEEP_RECENT_MESSAGES + 2),
        range(2, SUMMARY_KEEP_RECENT_MESSAGES + 2),
    )
    calls = []

    out = summarize_history({"messages": messages}, lambda s, m: calls.append(m) or "x")

    assert out == {}
    assert calls == []


def test_huge_tool_call_arguments_count_toward_the_trigger():
    # Gli argomenti di un tool call (un XML BPMN intero) finiscono nel prompt
    # vero: il conto che leggeva solo il testo li vedeva come zero token.
    huge_call = AIMessage(
        content="",
        tool_calls=[{"name": "update_bpmn", "args": {"xml": "parola " * 30_000}, "id": "call-1"}],
        id="m1",
    )
    messages = [
        HumanMessage(content="aggiorna il processo", id="m0"),
        huge_call,
        ToolMessage(content="ok", tool_call_id="call-1", id="m2"),
        AIMessage(content="fatto", id="m3"),
        HumanMessage(content="grazie", id="m4"),
        AIMessage(content="prego", id="m5"),
        HumanMessage(content="altro?", id="m6"),
        AIMessage(content="niente", id="m7"),
    ]
    assert len(messages) <= SUMMARY_TRIGGER_MESSAGE_COUNT

    out = summarize_history({"messages": messages}, lambda existing, old: "sintesi")

    assert out["running_summary"] == "sintesi"


def test_a_failed_summary_does_not_fail_the_turn():
    def broken(existing, old):
        raise TimeoutError("provider lento")

    messages = _thread(SUMMARY_TRIGGER_MESSAGE_COUNT + 2)
    out = summarize_history({"messages": messages, "running_summary": "prima"}, broken)

    summary = out["running_summary"]
    assert summary.startswith("prima")
    assert "non una sintesi" in summary
    assert "turno 0" in summary
    assert out["messages"], "lo stato deve comunque smettere di crescere"


def test_the_fallback_extract_has_a_ceiling():
    def broken(existing, old):
        raise TimeoutError("guasto")

    messages = _thread(SUMMARY_TRIGGER_MESSAGE_COUNT + 2, text="x" * 5_000)
    out = summarize_history({"messages": messages}, broken)

    assert len(out["running_summary"]) <= FALLBACK_TOTAL_CHARS + 300


def test_a_missing_operation_is_not_hidden_by_the_fallback():
    def unaccounted(existing, old):
        raise OperationNotOpen("nessuna operazione aperta")

    with pytest.raises(OperationNotOpen):
        summarize_history({"messages": _thread(SUMMARY_TRIGGER_MESSAGE_COUNT + 2)}, unaccounted)


def _provider_timeout() -> openai.APITimeoutError:
    return openai.APITimeoutError(request=httpx.Request("POST", "https://provider.test"))


def test_a_provider_timeout_falls_back_and_is_counted(caplog):
    degradation_counters.reset()
    messages = _thread(SUMMARY_TRIGGER_MESSAGE_COUNT + 2)

    def slow(existing, old):
        raise _provider_timeout()

    with caplog.at_level(logging.WARNING, logger="backend.agent"):
        out = summarize_history({"messages": messages}, slow)

    assert "non una sintesi" in out["running_summary"]
    assert degradation_counters.snapshot() == {"thread_summary:fallback_extract": 1}
    assert [r.levelno for r in caplog.records if r.name == "backend.agent"] == [logging.ERROR]


def test_a_programming_error_is_not_hidden_by_the_fallback():
    # Un difetto nostro non e' un guasto del provider: un estratto al posto
    # del riassunto lo nasconderebbe per sempre dietro un turno che funziona.
    def buggy(existing, old):
        raise TypeError("argomento sbagliato")

    with pytest.raises(TypeError):
        summarize_history({"messages": _thread(SUMMARY_TRIGGER_MESSAGE_COUNT + 2)}, buggy)
