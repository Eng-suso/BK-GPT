"""La spesa di un turno di chat si conta una volta sola.

Un tool della chat che chiama `llm.run()` gira dentro il grafo LangGraph. Il
gateway scrive la riga del suo compito; LangGraph intanto inoltra i pezzi di
quella chiamata nello stream del turno, con i loro `usage_metadata`. Il runtime
sommava tutto lo stream nella riga `chat_turn`: la stessa spesa finiva nel
registro due volte, e il turno di chat sembrava costare piu' di quanto costava.
"""

from __future__ import annotations

from typing import TypedDict

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.graph import END, START, StateGraph

from backend.llm import LlmTask, profile_for
from backend.llm_streaming import LEDGER_RECORDED_TAG, stream_to_final
from backend.services.agent_runtime import is_ledger_recorded
from backend.settings import settings


class _Model(BaseChatModel):
    """Un modello che risponde subito, con i token dove langchain li mette."""

    input_tokens: int

    @property
    def _llm_type(self) -> str:
        return "fake"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        usage = {
            "input_tokens": self.input_tokens,
            "output_tokens": 1,
            "total_tokens": self.input_tokens + 1,
        }
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="ok", usage_metadata=usage))])


class _State(TypedDict):
    step: str


def _usage_seen_by_the_turn(tool_model: _Model) -> dict[str, int]:
    """Gira un turno minimo e somma i token come fa il runtime della chat."""
    agent_model = _Model(input_tokens=10)

    def agent(_state):
        agent_model.invoke("domanda")
        return {"step": "agent"}

    def tools(_state):
        # Come `gateway.run`: lo stream interno, senza config esplicita.
        stream_to_final(tool_model, "lavoro del tool")
        return {"step": "tools"}

    graph = StateGraph(_State)
    graph.add_node("agent", agent)
    graph.add_node("tools", tools)
    graph.add_edge(START, "agent")
    graph.add_edge("agent", "tools")
    graph.add_edge("tools", END)

    seen: dict[str, int] = {}
    for mode, payload in graph.compile().stream({"step": ""}, stream_mode=["messages", "updates"]):
        if mode != "messages":
            continue
        chunk, metadata = payload
        usage = getattr(chunk, "usage_metadata", None)
        if usage and not is_ledger_recorded(metadata):
            node = metadata.get("langgraph_node") or ""
            seen[node] = seen.get(node, 0) + usage["input_tokens"]
    return seen


def test_una_chiamata_del_gateway_dentro_un_tool_non_si_somma_al_turno():
    gateway_model = _Model(input_tokens=1000, tags=[LEDGER_RECORDED_TAG])

    assert _usage_seen_by_the_turn(gateway_model) == {"agent": 10}


def test_una_chiamata_non_registrata_altrove_resta_nel_turno():
    # Il riassunto del thread e l'instradamento girano con i client della chat,
    # che non scrivono righe da soli: se il runtime li saltasse, sparirebbero.
    unrecorded_model = _Model(input_tokens=1000)

    assert _usage_seen_by_the_turn(unrecorded_model) == {"agent": 10, "tools": 1000}


@pytest.fixture()
def costruito(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "sk-test-non-usata")
    visti: dict = {}

    class _FakeChatOpenAI:
        def __init__(self, **kwargs):
            visti.update(kwargs)

    import langchain_openai

    monkeypatch.setattr(langchain_openai, "ChatOpenAI", _FakeChatOpenAI)
    return visti


@pytest.mark.parametrize("task", [LlmTask.PLAN_EXTRACTION, LlmTask.RETRIEVAL_RERANK, LlmTask.ENTITY_RESOLUTION])
def test_ogni_client_del_gateway_porta_il_tag(costruito, task):
    from backend.llm.gateway import _client

    _client(profile_for(task), None)

    assert LEDGER_RECORDED_TAG in costruito["tags"]


def test_i_client_della_chat_non_portano_il_tag(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "sk-test-non-usata")
    from backend.llm import chat_client

    client = chat_client(LlmTask.CHAT_TURN, model_name=settings.openai_model, streaming=True, tag="t")

    assert LEDGER_RECORDED_TAG not in (client.tags or [])
