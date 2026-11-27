"""La risposta arriva parola per parola anche quando nasce dentro un sotto-grafo.

Le risposte dei grafi consulente, progetto, processo e canvas si scrivono in
un sotto-grafo LangGraph. Senza `subgraphs=True` il runtime riceveva solo il
messaggio finito, a fine turno: un `delta` solo, dopo tutto il ragionamento
(docs/load-test/README.md). Qui c'e' un grafo LangGraph vero, con un modello
finto che scrive un token alla volta, e le due cose che non devono arrivare al
consulente:

- la passata di uno specialista (`findings_channel`), che scrive in un canale
  di stato e non in `messages`;
- la prima stesura di un rapporto che un controllo fa riscrivere
  (`process_report`): arriva solo la versione finale.
"""

from __future__ import annotations

import operator
from typing import Annotated

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, MessagesState, StateGraph

from backend.llm_streaming import unstreamed_config
from backend.services import agent_runtime

ANSWER = "La pratica si ferma alla seconda firma della direzione"
FINDING = "SEGRETO dello specialista che il consulente non deve leggere"
DRAFT = "BOZZA da riscrivere"
REPORT = "Rapporto finale con le fonti giuste"


class State(MessagesState):
    findings: Annotated[list[str], operator.add]


def _model(text: str) -> GenericFakeChatModel:
    return GenericFakeChatModel(messages=iter([AIMessage(content=text)]))


def _agent():
    specialist_model, answer_model = _model(FINDING), _model(ANSWER)
    draft_model, report_model = _model(DRAFT), _model(REPORT)

    def specialist(state: State, config: RunnableConfig) -> dict:
        text = "".join(c.content for c in specialist_model.stream("x", config=unstreamed_config(config)))
        return {"findings": [text]}

    def chatbot(state: State, config: RunnableConfig) -> dict:
        response = None
        for chunk in answer_model.stream("x", config=config):
            response = chunk if response is None else response + chunk
        return {"messages": [response]}

    def process_report(state: State, config: RunnableConfig) -> dict:
        report_config = unstreamed_config(config)
        draft_model.invoke("x", config=report_config)  # scartata dal controllo
        return {"messages": [report_model.invoke("x", config=report_config)]}

    child = StateGraph(State)
    child.add_node("specialist", specialist)
    child.add_node("chatbot", chatbot)
    child.add_node("process_report", process_report)
    child.add_edge(START, "specialist")
    child.add_edge("specialist", "chatbot")
    child.add_edge("chatbot", "process_report")
    child.add_edge("process_report", END)

    parent = StateGraph(State)
    parent.add_node("consulting_subgraph", child.compile())
    parent.add_edge(START, "consulting_subgraph")
    parent.add_edge("consulting_subgraph", END)
    return parent.compile()


def _events(monkeypatch):
    monkeypatch.setattr(agent_runtime, "get_agent", lambda *_a, **_k: _agent())
    monkeypatch.setattr(agent_runtime, "langsmith_tracing_enabled", lambda: False)
    return list(
        agent_runtime.stream_agent_events(
            thread_id="thread-sottografo",
            model_name="gpt-5.6-luna",
            messages=[{"role": "user", "content": "dove si ferma la pratica?"}],
            scope=None,
        )
    )


def test_the_answer_written_in_a_subgraph_streams_token_by_token(monkeypatch):
    deltas = [e for e in _events(monkeypatch) if e.type == "delta"]

    answer_deltas = [e for e in deltas if e.node == "chatbot"]
    assert len(answer_deltas) > 3, "la risposta deve arrivare a pezzi, non in un blocco"
    assert "".join(e.content for e in answer_deltas) == ANSWER


def test_what_is_not_for_the_consultant_never_reaches_the_stream(monkeypatch):
    text = "".join(e.content or "" for e in _events(monkeypatch) if e.type == "delta")

    assert FINDING not in text
    assert DRAFT not in text
    # Il rapporto finale arriva intero a fine nodo, dopo la risposta.
    assert text == ANSWER + REPORT


def _metered_model(text: str) -> GenericFakeChatModel:
    from backend.llm_streaming import TURN_METERED_TAG

    usage = {"input_tokens": 120, "output_tokens": 30, "total_tokens": 150}
    return GenericFakeChatModel(
        messages=iter([AIMessage(content=text, usage_metadata=usage)]), tags=[TURN_METERED_TAG]
    )


def test_a_call_kept_out_of_the_stream_still_counts_for_the_spending_limit():
    """La passata muta e' pagata: entra nella spesa del turno, cioe' nel limite della persona."""
    meter = agent_runtime.UnstreamedUsageMeter()
    config = {"callbacks": [meter], "metadata": {"langgraph_node": "process_discovery_agent"}}

    _metered_model(FINDING).invoke("x", config=unstreamed_config(config))

    assert meter.usage_by_node["process_discovery_agent"]["input_tokens"] == 120
    assert meter.usage_by_node["process_discovery_agent"]["output_tokens"] == 30


def test_a_streamed_call_is_left_to_the_stream_so_it_is_not_counted_twice():
    meter = agent_runtime.UnstreamedUsageMeter()

    _metered_model(ANSWER).invoke("x", config={"callbacks": [meter]})

    assert meter.usage_by_node == {}


def test_the_routers_of_the_subgraphs_are_routing_not_answer():
    from backend.llm import LlmTask

    for node in ("consult_router", "project_router", "process_router", "canvas_router"):
        assert agent_runtime.task_for_node(node) is LlmTask.CONTEXT_ROUTING
    assert agent_runtime.is_internal_agent_node("tools")
    assert agent_runtime.is_internal_agent_node("consult_router")
