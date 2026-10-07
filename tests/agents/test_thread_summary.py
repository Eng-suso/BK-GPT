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

import backend.agent as agent_module
from backend.agent import (
    FALLBACK_LINE_CHARS,
    FALLBACK_SUMMARY_MAX_CHARS,
    FALLBACK_TOTAL_CHARS,
    SUMMARY_KEEP_RECENT_MESSAGES,
    SUMMARY_MAX_TOKENS,
    SUMMARY_TRIGGER_MESSAGE_COUNT,
    _history_tokens,
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

    # Abbastanza righe tagliate da superare anche il tetto totale.
    lines_over_total = FALLBACK_TOTAL_CHARS // FALLBACK_LINE_CHARS + 5
    messages = _thread(SUMMARY_KEEP_RECENT_MESSAGES + lines_over_total, text="x" * 5_000)
    out = summarize_history({"messages": messages}, broken)

    header, extract = out["running_summary"].split("\n", 1)
    assert header.startswith("[Riassunto automatico non disponibile")
    # Il tetto totale taglia dalla testa e lo dichiara con "...".
    assert extract.startswith("...")
    assert len(extract) == len("...") + FALLBACK_TOTAL_CHARS
    # Ogni riga intera ha il suo tetto; la prima e' gia' tagliata da quello totale.
    for line in extract.split("\n")[1:]:
        assert len(line) <= FALLBACK_LINE_CHARS + len("...")
        assert line.endswith("...")


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


def test_messages_without_id_are_not_summarized_twice():
    # Senza id un messaggio non si puo' togliere dallo stato: resta in testa,
    # gia' dentro il riassunto. Il contatore deve saltarlo al giro dopo.
    messages = _thread(SUMMARY_TRIGGER_MESSAGE_COUNT + 2)
    for i in range(2):
        messages[i] = type(messages[i])(content=f"senza id {i}")
    cutoff = len(messages) - SUMMARY_KEEP_RECENT_MESSAGES

    first = summarize_history({"messages": messages}, lambda existing, old: "sintesi")

    removed = {op.id for op in first["messages"]}
    assert removed == {m.id for m in messages[2:cutoff]}
    assert first["summarized_message_count"] == 2

    kept = [m for m in messages if m.id not in removed]
    new = [HumanMessage(content=f"nuovo {i}", id=f"n{i}") for i in range(SUMMARY_KEEP_RECENT_MESSAGES)]
    seen: list = []
    summarize_history(
        {"messages": kept + new, "summarized_message_count": first["summarized_message_count"]},
        lambda existing, old: seen.extend(old) or "sintesi 2",
    )

    assert seen, "il secondo giro deve riassumere i messaggi usciti dalla coda"
    assert not [m for m in seen if m.id is None]


def test_a_blank_summary_falls_back_to_the_extract():
    degradation_counters.reset()
    messages = _thread(SUMMARY_TRIGGER_MESSAGE_COUNT + 2)

    out = summarize_history({"messages": messages, "running_summary": "prima"}, lambda e, o: "  \n ")

    assert out["running_summary"].startswith("prima")
    assert "non una sintesi" in out["running_summary"]
    assert degradation_counters.snapshot() == {"thread_summary:empty_summary": 1}


def test_a_repeated_call_summarizes_only_what_is_new():
    messages = _thread(SUMMARY_TRIGGER_MESSAGE_COUNT + 4)
    seen: list = []

    out = summarize_history(
        {"messages": messages, "summarized_message_count": 3, "running_summary": "prima"},
        lambda existing, old: seen.append((existing, old)) or "dopo",
    )

    cutoff = len(messages) - SUMMARY_KEEP_RECENT_MESSAGES
    assert seen == [("prima", messages[3:cutoff])]
    assert out["running_summary"] == "dopo"


def test_nothing_new_to_summarize_is_a_no_op():
    messages = _thread(SUMMARY_TRIGGER_MESSAGE_COUNT + 2)
    cutoff = len(messages) - SUMMARY_KEEP_RECENT_MESSAGES
    calls = []

    out = summarize_history(
        {"messages": messages, "summarized_message_count": cutoff},
        lambda s, m: calls.append(m) or "x",
    )

    assert out == {}
    assert calls == []


@pytest.mark.parametrize(
    ("count", "summarized"),
    [(SUMMARY_TRIGGER_MESSAGE_COUNT, False), (SUMMARY_TRIGGER_MESSAGE_COUNT + 1, True)],
)
def test_the_message_count_threshold_is_exclusive(count, summarized):
    out = summarize_history({"messages": _thread(count)}, lambda existing, old: "sintesi")

    assert ("running_summary" in out) is summarized


@pytest.mark.parametrize(("margin", "summarized"), [(0, False), (1, True)])
def test_the_token_threshold_is_exclusive(monkeypatch, margin, summarized):
    messages = _thread(SUMMARY_KEEP_RECENT_MESSAGES + 2)
    region_tokens = _history_tokens(messages[:2])
    monkeypatch.setattr(agent_module, "SUMMARY_TRIGGER_TOKENS", region_tokens - margin)

    out = summarize_history({"messages": messages}, lambda existing, old: "sintesi")

    assert ("running_summary" in out) is summarized


def test_an_oversized_summary_is_not_persisted():
    # Il riassunto finisce in ogni prompt successivo: un testo fuori misura
    # (il modello che ripete la trascrizione) non entra nello stato.
    degradation_counters.reset()
    messages = _thread(SUMMARY_TRIGGER_MESSAGE_COUNT + 2)

    out = summarize_history(
        {"messages": messages, "running_summary": "prima"},
        lambda existing, old: "parola " * (SUMMARY_MAX_TOKENS + 1),
    )

    assert out["running_summary"].startswith("prima")
    assert "non una sintesi" in out["running_summary"]
    assert degradation_counters.snapshot() == {"thread_summary:oversized_summary": 1}


def test_consecutive_fallbacks_do_not_grow_the_summary_without_bound():
    # Ogni ripiego aggiungeva il suo estratto al riassunto di prima: con il
    # provider giu' per qualche turno il riassunto cresceva a ogni giro, e con
    # lui ogni prompt successivo.
    def broken(existing, old):
        raise TimeoutError("provider giu'")

    summary = "Obiettivo: mappare il processo acquisti."
    for turn in range(12):
        messages = _thread(SUMMARY_TRIGGER_MESSAGE_COUNT + 20, text=f"turno{turn} " + "x" * 400)
        summary = summarize_history({"messages": messages, "running_summary": summary}, broken)[
            "running_summary"
        ]

    assert len(summary) <= FALLBACK_SUMMARY_MAX_CHARS
    # Resta la sintesi del modello in testa e l'estratto piu' recente in coda.
    assert summary.startswith("Obiettivo: mappare il processo acquisti.")
    assert "turno11" in summary
    assert "estratti precedenti omessi" in summary


def test_the_fallback_extract_does_not_carry_tool_results_to_the_consultant():
    # L'esito di un tool e' fatto per il modello: id, XML, nomi di azione. Il
    # riassunto finisce nel contesto della chat, e il modello potrebbe
    # ripeterlo al consulente.
    def broken(existing, old):
        raise TimeoutError("provider giu'")

    messages = [
        HumanMessage(content="Aggiorna il processo acquisti", id="m0"),
        AIMessage(
            content="",
            tool_calls=[{"name": "manage_canvas_bpmn_model", "args": {"bpmn_model_id": "bpmn-7f3a"}, "id": "c1"}],
            id="m1",
        ),
        ToolMessage(
            content='{"action": "manage_canvas_bpmn_model", "bpmn_model_id": "bpmn-7f3a", '
            '"xml": "<definitions/>", "readiness": 0.42}',
            tool_call_id="c1",
            id="m2",
        ),
        AIMessage(content="Ho aggiornato il processo acquisti.", id="m3"),
        *_thread(SUMMARY_TRIGGER_MESSAGE_COUNT + 2)[4:],
    ]
    for i, message in enumerate(messages[4:], start=4):
        message.id = f"m{i}"

    summary = summarize_history({"messages": messages}, broken)["running_summary"]

    assert "Aggiorna il processo acquisti" in summary
    assert "Ho aggiornato il processo acquisti." in summary
    for internal in ("manage_canvas_bpmn_model", "bpmn-7f3a", "<definitions/>", "readiness"):
        assert internal not in summary

