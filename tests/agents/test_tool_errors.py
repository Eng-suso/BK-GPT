"""Un tool che fallisce: il modello legge perche', il confine ferma il turno.

Prima ogni `ValueError` di un tool ("Modello BPMN non trovato",
"element_id obbligatorio") usciva dal `ToolNode` e faceva cadere il turno: il
consulente vedeva un errore generico e il modello non poteva correggersi.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from backend.graphs.tool_errors import report_tool_error


def _run(tool_fn):
    """Il nodo dei tool come lo monta `build_tool_chat_subgraph`, in un grafo minimo."""
    wrapped = tool(tool_fn)
    graph = StateGraph(MessagesState)
    graph.add_node("tools", ToolNode([wrapped], handle_tool_errors=report_tool_error))
    graph.add_edge(START, "tools")
    graph.add_edge("tools", END)
    call = {"name": wrapped.name, "args": {}, "id": "call-1", "type": "tool_call"}
    state = graph.compile().invoke({"messages": [AIMessage(content="", tool_calls=[call])]})
    return state["messages"][-1]


def test_a_tool_that_refuses_the_request_answers_the_model():
    def aggiorna_elemento() -> str:
        """Aggiorna un elemento del canvas."""
        raise ValueError("element_id obbligatorio per update_element.")

    message = _run(aggiorna_elemento)

    assert "element_id obbligatorio per update_element." in message.content
    assert "Non ripetere la stessa chiamata" in message.content


def test_a_boundary_still_stops_the_turn():
    from backend.agents.scope_guard import ScopeViolation

    def scrivi_altrove() -> str:
        """Scrive fuori dallo scope."""
        raise ScopeViolation("project_id fuori scope")

    with pytest.raises(ScopeViolation):
        _run(scrivi_altrove)


def test_a_write_the_mode_forbids_still_stops_the_turn():
    from backend.agents.chat_mode import WriteNotAllowedInMode

    def scrivi() -> str:
        """Scrive nel workspace."""
        raise WriteNotAllowedInMode("modalita' di sola lettura")

    with pytest.raises(WriteNotAllowedInMode):
        _run(scrivi)


def test_arguments_outside_the_tool_schema_still_reach_the_model():
    """Rilievo CodeRabbit sulla PR #62: il gestore di default di LangGraph
    restituiva gia' al modello gli argomenti non validi (ToolInvocationError).
    Sostituendolo, quel caso non deve tornare a far cadere il turno."""

    def rinomina_elemento(element_id: str, name: str) -> str:
        """Rinomina un elemento del canvas."""
        return f"{element_id} -> {name}"

    message = _run(rinomina_elemento)  # chiamata senza argomenti: schema violato

    assert "element_id" in message.content


def test_a_version_conflict_is_logged_before_it_reaches_the_model(caplog):
    from backend.agents.run_context import BpmnVersionConflict

    with caplog.at_level("INFO", logger="backend.graphs.tool_errors"):
        result = report_tool_error(BpmnVersionConflict("rileggi il canvas salvato"))

    assert result.startswith("Modifica non salvata")
    assert any("conflitto di versione" in record.getMessage() for record in caplog.records)
