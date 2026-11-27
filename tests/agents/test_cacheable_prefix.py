"""Il prompt di uno specialista comincia con la parte fissa, sempre uguale.

Il fornitore fattura a un decimo i token di un prefisso gia' visto. Conta quindi
l'ordine: tutto cio' che non cambia (contratto dello specialista, memoria
procedurale) deve stare prima di cio' che cambia (contesto, storia, passi del
turno). Il contratto in coda veniva rimandato a prezzo pieno a ogni passo.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool

from backend.graphs.common import ConversationState, build_tool_chat_subgraph

CONTRACT = "Contratto dello specialista: testo fisso."
PROCEDURAL = "Memoria procedurale: testo fisso."


@tool
def look_up(note: str) -> str:
    """Un tool qualsiasi, per avere un secondo passo nel turno."""
    return f"letto: {note}"


class _TwoSteps:
    """Chiede un tool al primo passo e conclude al secondo; ricorda i prompt."""

    def __init__(self) -> None:
        self.prompts: list[list] = []

    def stream(self, messages, config=None):  # noqa: ARG002 - firma del runtime
        self.prompts.append(list(messages))
        if len(self.prompts) == 1:
            yield AIMessage(content="", tool_calls=[{"name": "look_up", "args": {"note": "x"}, "id": "c1"}])
        else:
            yield AIMessage(content="fatto")


def _context(state):
    return [SystemMessage(content=PROCEDURAL), SystemMessage(content="scope che cambia"), *state["messages"]]


def test_contract_opens_the_prompt_and_every_step_extends_the_one_before():
    llm = _TwoSteps()
    graph = build_tool_chat_subgraph(
        state_schema=ConversationState,
        tools=[look_up],
        llm_with_tools=llm,
        build_context_messages=_context,
        subgraph_contract=CONTRACT,
        agent_node_name="test_agent",
        tool_node_name="test_tools",
    )

    graph.invoke({"messages": [HumanMessage(content="vai")]})

    first, second = llm.prompts
    assert [m.content for m in first[:2]] == [CONTRACT, PROCEDURAL]
    # Il secondo passo e' il primo piu' il tool chiamato e il suo risultato:
    # tutto il primo prompt e' un prefisso, quindi tutto e' in cache.
    assert [m.content for m in second[: len(first)]] == [m.content for m in first]
    assert len(second) == len(first) + 2
