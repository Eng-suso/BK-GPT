"""L'impronta del contesto di scope arriva al runtime del turno (P1.3c).

`assemble()` calcola l'impronta del contesto, ma la riga di consumo la scrive
il runtime a fine turno, in un altro punto del codice e, dentro LangGraph, in
un altro thread. Qui si prova il tragitto: il prompt di scope la annota, il
raccoglitore del turno la vede, anche da un nodo del grafo.
"""

from __future__ import annotations

import hashlib
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from backend.agents.context_budget import collect_context_fingerprints, note_context_fingerprint
from backend.agents.primary_scope import build_scope_system_prompt

_STATE = {"scope_type": "consultant", "chat_mode": "conversation"}


def test_the_scope_prompt_notes_the_fingerprint_of_what_it_returns():
    with collect_context_fingerprints() as seen:
        prompt = build_scope_system_prompt(_STATE)

    assert seen == [hashlib.sha256(prompt.encode("utf-8")).hexdigest()]


def test_outside_a_turn_nothing_is_collected():
    build_scope_system_prompt(_STATE)

    with collect_context_fingerprints() as seen:
        pass

    assert seen == []


def test_a_graph_node_reaches_the_collector_of_its_turn():
    # I nodi sincroni di LangGraph girano in un pool di thread: il raccoglitore
    # deve arrivarci come ci arriva l'operazione del turno.
    class _State(TypedDict):
        done: bool

    def node(_state: _State) -> dict:
        note_context_fingerprint("f" * 64)
        return {"done": True}

    graph = StateGraph(_State)
    graph.add_node("node", node)
    graph.add_edge(START, "node")
    graph.add_edge("node", END)

    with collect_context_fingerprints() as seen:
        list(graph.compile().stream({"done": False}))

    assert seen == ["f" * 64]


def test_turns_do_not_share_a_collector():
    with collect_context_fingerprints() as first:
        note_context_fingerprint("a" * 64)
    with collect_context_fingerprints() as second:
        note_context_fingerprint("b" * 64)

    assert (first, second) == (["a" * 64], ["b" * 64])


def test_the_turn_ledger_row_carries_the_last_context_fingerprint(monkeypatch):
    from backend.llm import LlmTask
    from backend.services import agent_runtime

    class _Chunk:
        type = "AIMessageChunk"

        def __init__(self, usage_metadata):
            self.content = ""
            self.usage_metadata = usage_metadata

    class _Agent:
        # Due chiamate al modello nello stesso turno: il contesto della seconda
        # e' quello su cui il modello ha scritto la risposta.
        def stream(self, _input, *, config, stream_mode):
            usage = {"input_tokens": 5, "output_tokens": 1, "total_tokens": 6}
            note_context_fingerprint("1" * 64)
            yield _Chunk(usage), {"langgraph_node": "consult_macro_agent"}
            note_context_fingerprint("2" * 64)
            yield _Chunk(usage), {"langgraph_node": "consult_macro_agent"}
            yield _Chunk(usage), {"langgraph_node": "classify_and_select_context"}

    recorded: dict = {}

    def _record(task, usage, **kwargs):
        recorded[task] = kwargs

    monkeypatch.setattr(agent_runtime, "get_agent", lambda *_a, **_k: _Agent())
    monkeypatch.setattr(agent_runtime, "langsmith_tracing_enabled", lambda: False)
    monkeypatch.setattr(agent_runtime, "record_streamed_usage", _record)

    list(
        agent_runtime.stream_agent_events(
            thread_id="thread-fingerprint",
            model_name="gpt-5.6-luna",
            messages=[{"role": "user", "content": "ciao"}],
            scope=None,
        )
    )

    assert recorded[LlmTask.CHAT_TURN]["context_fingerprint"] == "2" * 64
    # L'instradamento non riceve il contesto di scope: niente impronta.
    assert recorded[LlmTask.CONTEXT_ROUTING]["context_fingerprint"] is None
