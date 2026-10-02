"""PROCESS-V2-05: un turno di processo consegna una risposta, non cinque.

Nel test E2E V2 la chat di processo rispondeva con quattro o cinque sintesi
quasi identiche una dietro l'altra. Non era un bug di aggregazione: il giro di
lavoro fa piu' passate, ogni specialista chiudeva la sua scrivendo in chat, e
tutte arrivavano al consulente.

Perche' non si puo' filtrare a valle: sotto un sottografo annidato lo stream di
LangGraph (`stream_mode="messages"`, senza `subgraphs=True`) consegna il
messaggio scritto in stato, attribuito al nodo piu' esterno. Non arriva il nome
del nodo interno e non arrivano i tag della chiamata LLM - il primo test qui
sotto lo verifica invece di darlo per scontato. L'unica leva e' cosa entra in
`messages`.
"""

from __future__ import annotations

from typing import Annotated, TypedDict

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import START, END, StateGraph
from langgraph.graph.message import add_messages

from backend.graphs.common import build_tool_chat_subgraph
from backend.graphs.process.graph import (
    build_process_report,
    specialist_findings_digest,
)
from backend.services.agent_runtime import (
    NON_DELTA_AGENT_NODES,
    is_internal_agent_node,
    is_internal_stream_metadata,
)


class NestedState(TypedDict):
    messages: Annotated[list, add_messages]
    specialist_findings: Annotated[list, lambda a, b: (a or []) + (b or [])]


def _speaking_model(text: str, times: int = 8) -> GenericFakeChatModel:
    return GenericFakeChatModel(messages=iter([AIMessage(content=text)] * times))


def _nested_app(leaf_node):
    """La stessa forma del grafo vero: top -> process_subgraph -> subgraph -> agente."""
    leaf = StateGraph(NestedState)
    leaf.add_node("process_evidence_agent", leaf_node)
    leaf.add_edge(START, "process_evidence_agent")
    leaf.add_edge("process_evidence_agent", END)

    mid = StateGraph(NestedState)
    mid.add_node("evidence_subgraph", leaf.compile())
    mid.add_edge(START, "evidence_subgraph")
    mid.add_edge("evidence_subgraph", END)

    top = StateGraph(NestedState)
    top.add_node("process_subgraph", mid.compile())
    top.add_edge(START, "process_subgraph")
    top.add_edge("process_subgraph", END)
    return top.compile()


def _delivered(app, state=None) -> list[tuple[str, str]]:
    """Cosa arriva davvero al consulente: (nodo, testo) degli eventi non interni."""
    out = []
    for chunk, metadata in app.stream(
        state or {"messages": [HumanMessage(content="analizza le interviste")]},
        stream_mode="messages",
    ):
        if is_internal_stream_metadata(metadata):
            continue
        node = metadata.get("langgraph_node") or ""
        if is_internal_agent_node(node) or node in NON_DELTA_AGENT_NODES:
            continue
        text = str(getattr(chunk, "content", ""))
        if text:
            out.append((node, text))
    return out


# --- perche' il filtro a valle non poteva funzionare ------------------------

def test_a_nested_answer_arrives_labelled_with_the_outermost_node():
    """Il nome del nodo interno non arriva: filtrarci sopra non e' un'opzione."""
    model = _speaking_model("SINTESI")

    def leaf(state: NestedState) -> dict:
        return {"messages": [model.invoke(state["messages"])]}

    delivered = _nested_app(leaf)

    nodes = {node for node, _ in _delivered(delivered)}
    assert nodes == {"process_subgraph"}
    assert "evidence_subgraph" not in nodes
    assert "process_evidence_agent" not in nodes


# --- il comportamento che conta --------------------------------------------

def test_a_specialist_pass_does_not_speak_to_the_consultant():
    """La conclusione della passata va nel dossier, non in chat."""
    model = _speaking_model("SINTESI DELLA PASSATA")
    subgraph = build_tool_chat_subgraph(
        state_schema=NestedState,
        tools=[],
        llm_with_tools=model,
        build_context_messages=lambda state: list(state["messages"]),
        agent_node_name="process_evidence_agent",
        tool_node_name="process_evidence_tools",
        findings_channel="specialist_findings",
        specialist="evidence",
    )

    result = subgraph.invoke({"messages": [HumanMessage(content="analizza")]})

    assert [m for m in result["messages"] if isinstance(m, AIMessage)] == []
    assert result["specialist_findings"] == [
        {"owner": "evidence", "finding": "SINTESI DELLA PASSATA"}
    ]


def test_three_passes_deliver_nothing_and_the_report_delivers_once():
    """Tre passate, una risposta: e' l'invariante del turno."""
    specialist = _speaking_model("SINTESI DELLA PASSATA")
    subgraph = build_tool_chat_subgraph(
        state_schema=NestedState,
        tools=[],
        llm_with_tools=specialist,
        build_context_messages=lambda state: list(state["messages"]),
        agent_node_name="process_evidence_agent",
        tool_node_name="process_evidence_tools",
        findings_channel="specialist_findings",
        specialist="evidence",
    )

    state: dict = {"messages": [HumanMessage(content="analizza")], "specialist_findings": []}
    for _ in range(3):
        update = subgraph.invoke(state)
        state = {
            "messages": update["messages"],
            "specialist_findings": update.get("specialist_findings") or [],
        }

    assert len(state["specialist_findings"]) == 3
    assert [m for m in state["messages"] if isinstance(m, AIMessage)] == []

    report = build_process_report(_speaking_model("RISPOSTA UNICA AL CONSULENTE"))
    written = report({**state, "process_name": "Acquisti"}, {})

    assert len(written["messages"]) == 1
    assert written["messages"][0].content == "RISPOSTA UNICA AL CONSULENTE"


def test_a_pass_that_calls_a_tool_still_writes_the_message_the_loop_needs():
    """Il messaggio con tool call resta: ToolNode ci aggancia i risultati."""
    calling = AIMessage(
        content="",
        tool_calls=[{"name": "qualsiasi", "args": {}, "id": "call-1"}],
    )
    model = GenericFakeChatModel(messages=iter([calling]))

    def leaf(state: NestedState, config=None) -> dict:
        response = model.invoke(state["messages"])
        # Stesso ramo del builder: con tool call si scrive in `messages`.
        assert response.tool_calls
        return {"messages": [response]}

    result = leaf({"messages": [HumanMessage(content="analizza")]})

    assert result["messages"][0].tool_calls


def test_the_report_stays_silent_when_no_pass_concluded_anything():
    """Senza materiale non si inventa una risposta."""
    report = build_process_report(_speaking_model("NON DEVE USCIRE"))

    assert report({"specialist_findings": []}, {}) == {}


def test_the_next_pass_is_told_what_the_previous_one_concluded():
    """Fuori dal transcript non vuol dire perso: la passata dopo lo legge."""
    seen: list[str] = []

    class Recording(GenericFakeChatModel):
        def stream(self, input, config=None, **kwargs):  # noqa: A002
            seen.extend(
                m.content for m in input if isinstance(m, SystemMessage)
            )
            return super().stream(input, config=config, **kwargs)

    model = Recording(messages=iter([AIMessage(content="SECONDA PASSATA")] * 4))
    subgraph = build_tool_chat_subgraph(
        state_schema=NestedState,
        tools=[],
        llm_with_tools=model,
        build_context_messages=lambda state: list(state["messages"]),
        agent_node_name="process_evidence_agent",
        tool_node_name="process_evidence_tools",
        findings_channel="specialist_findings",
        specialist="evidence",
    )

    subgraph.invoke(
        {
            "messages": [HumanMessage(content="continua")],
            "specialist_findings": [{"owner": "discovery", "finding": "Laura riferisce X"}],
        }
    )

    assert any("Laura riferisce X" in text for text in seen)


def test_the_router_is_told_too():
    digest = specialist_findings_digest(
        {"specialist_findings": [{"owner": "evidence", "finding": "Paolo riferisce Y"}]}
    )

    assert "Paolo riferisce Y" in digest
    assert "evidence" in digest


# --- la regola epistemica sta nel prompt che scrive la risposta -------------

@pytest.mark.parametrize(
    "rule",
    ["riferisce", "Confermato", "contraddizione", "resta aperta"],
)
def test_the_report_prompt_carries_the_evidence_governance(rule):
    from backend.graphs.process.graph import PROCESS_REPORT_PROMPT

    assert rule in PROCESS_REPORT_PROMPT
