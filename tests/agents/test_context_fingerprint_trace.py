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
