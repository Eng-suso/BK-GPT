"""Il runtime ferma l'agente, anche quando l'agente non si ferma da solo.

Il ciclo agente -> tool -> agente non aveva nessun tetto: finiva quando il
modello smetteva di chiedere tool. Un modello che continua a chiedere - per un
difetto di prompt, per un tool che risponde sempre "riprova", o semplicemente
perche' il lavoro e' piu' grande della finestra - girava finche' qualcuno
chiudeva la pagina.

Qui si verifica la garanzia di terminazione, che e' del runtime e non del
modello: tre limiti, e un turno che si ferma dicendo perche' invece di
dichiararsi finito.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool

from backend.graphs.agent_budget import (
    BUDGET_EXHAUSTED_MESSAGE,
    EXHAUSTED_KEY,
    STARTED_AT_KEY,
    STEPS_KEY,
    TOOL_CALLS_KEY,
    AgentBudget,
    exhausted_reason,
)
from backend.graphs.common import ConversationState, build_tool_chat_subgraph
from backend.settings import settings


BUDGET = AgentBudget(max_decision_steps=3, max_tool_calls=10, deadline_seconds=60.0)


@tool
def always_more_work(note: str) -> str:
    """Un tool che non conclude mai: risponde e invita a continuare."""
    return f"{note}: servono altri accertamenti."


class _NeverFinishes:
    """Un modello che chiede sempre un altro tool. Esiste, e non e' un'ipotesi."""

    def __init__(self) -> None:
        self.calls = 0

    def stream(self, messages, config=None):  # noqa: ARG002 - firma del runtime
        self.calls += 1
        yield AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "always_more_work",
                    "args": {"note": f"giro {self.calls}"},
                    "id": f"call_{self.calls}",
                }
            ],
        )


def test_steps_budget_stops_the_loop(monkeypatch):
    """Un agente che chiede tool all'infinito viene fermato dal runtime."""
    monkeypatch.setattr(settings, "agent_max_decision_steps", 3)
    monkeypatch.setattr(settings, "agent_max_tool_calls", 50)
    monkeypatch.setattr(settings, "agent_run_deadline_seconds", 60.0)

    llm = _NeverFinishes()
    graph = build_tool_chat_subgraph(
        state_schema=ConversationState,
        tools=[always_more_work],
        llm_with_tools=llm,
        build_context_messages=lambda state: list(state["messages"]),
        agent_node_name="test_agent",
        tool_node_name="test_tools",
    )

    result = graph.invoke({"messages": [HumanMessage(content="vai")]})

    assert llm.calls == 3, "il modello non deve essere invocato oltre il budget di passi"
    assert result[EXHAUSTED_KEY], "lo stop deve restare dichiarato in stato"
    assert result["messages"][-1].content == BUDGET_EXHAUSTED_MESSAGE
    # Il transcript resta coerente: l'ultimo messaggio non e' una tool call
    # rimasta senza risposta, che al turno dopo il provider rifiuterebbe.
    assert not getattr(result["messages"][-1], "tool_calls", None)


def test_tool_call_budget_stops_the_loop(monkeypatch):
    """Leggere all'infinito senza concludere e' l'altro modo di non finire."""
    monkeypatch.setattr(settings, "agent_max_decision_steps", 50)
    monkeypatch.setattr(settings, "agent_max_tool_calls", 2)
    monkeypatch.setattr(settings, "agent_run_deadline_seconds", 60.0)

    llm = _NeverFinishes()
    graph = build_tool_chat_subgraph(
        state_schema=ConversationState,
        tools=[always_more_work],
        llm_with_tools=llm,
        build_context_messages=lambda state: list(state["messages"]),
        agent_node_name="test_agent",
        tool_node_name="test_tools",
    )

    result = graph.invoke({"messages": [HumanMessage(content="vai")]})

    assert llm.calls == 2
    assert "strumenti" in result[EXHAUSTED_KEY]


def test_deadline_is_measured_from_the_start_of_the_run():
    """La scadenza si misura dall'inizio del run, non dall'ultimo passo.

    Rifissare l'istante di partenza a ogni giro renderebbe la scadenza sempre
    lontana, cioe' inesistente.
    """
    state = {STARTED_AT_KEY: 1_000.0, STEPS_KEY: 1, TOOL_CALLS_KEY: 1}

    assert exhausted_reason(state, BUDGET, now=1_030.0) is None
    reason = exhausted_reason(state, BUDGET, now=1_061.0)
    assert reason and "Tempo massimo" in reason


def test_a_fresh_state_has_a_full_budget():
    """Un turno che comincia non e' un turno gia' scaduto."""
    assert exhausted_reason({}, BUDGET) is None


def test_budget_reads_server_policy(monkeypatch):
    monkeypatch.setattr(settings, "agent_max_decision_steps", 7)
    monkeypatch.setattr(settings, "agent_max_tool_calls", 9)
    monkeypatch.setattr(settings, "agent_run_deadline_seconds", 42.0)

    budget = AgentBudget.from_settings()

    assert (budget.max_decision_steps, budget.max_tool_calls, budget.deadline_seconds) == (
        7,
        9,
        42.0,
    )
