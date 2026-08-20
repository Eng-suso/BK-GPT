from backend.graphs.consulting.graph import parse_router_json
from backend.graphs.consulting.subgraphs.clients.tools import clients_tools
from backend.graphs.consulting.subgraphs.clients.state import ClientsState
from backend.graphs.consulting.subgraphs.home.tools import home_tools
from backend.graphs.consulting.subgraphs.home.state import HomeState
from backend.graphs.consulting.subgraphs.setup.tools import setup_tools
from backend.graphs.consulting.subgraphs.setup.state import SetupState
from backend.graphs.consulting.tools import consultant_tools
from backend.toolsets.workspace import (
    get_workspace_overview,
    manage_client_record,
    prepare_home_dashboard_update,
    validate_initial_workspace_setup,
)


def test_parse_router_json_returns_structured_state():
    result = parse_router_json(
        """
        {
          "route": "clients",
          "confidence": 0.82,
          "needs_clarification": false,
          "clarification_question": null,
          "entity_hints": {"client": "ACME"},
          "consulting_mode": "delegation",
          "consulting_objective": "handle ACME client",
          "expected_result": "create or inspect client",
          "reason": "Client-level operation"
        }
        """,
        user_request="crea cliente ACME",
    )

    assert result["consulting_route"] == "clients"
    assert result["consulting_mode"] == "delegation"
    assert result["consulting_objective"] == "handle ACME client"
    assert result["delegation_target"] == "clients_subgraph"
    assert result["routing_confidence"] == 0.82
    assert result["needs_clarification"] is False
    assert result["entity_hints"] == {"client": "ACME"}
    assert result["delegation_payload"]["user_request"] == "crea cliente ACME"
    assert result["delegation_payload"]["expected_result"] == "create or inspect client"
    assert result["routing_trace"][0]["route"] == "clients"
    assert result["delegation_events"][0]["target"] == "clients_subgraph"


def test_parse_router_json_falls_back_to_direct_for_invalid_route():
    result = parse_router_json('{"route":"unknown","confidence":5}')

    assert result["consulting_route"] == "direct"
    assert result["delegation_target"] is None
    assert result["routing_confidence"] == 1.0


def test_workspace_overview_tool_is_read_only_snapshot():
    result = get_workspace_overview.invoke({})

    assert "Workspace overview" in result
    assert "client_count" in result
    assert "project_count" in result


def test_consulting_subgraph_states_define_operational_fields():
    assert "priority_items" in HomeState.__annotations__
    assert "duplicate_candidates" in ClientsState.__annotations__
    assert "created_records" in SetupState.__annotations__


def test_consulting_toolsets_are_small_and_owned():
    assert len(consultant_tools) <= 8
    assert len(home_tools) <= 8
    assert len(clients_tools) <= 8
    assert len(setup_tools) <= 8

    assert {tool.name for tool in clients_tools} == {
        "get_workspace_overview",
        "list_workspace_clients",
        "manage_client_record",
    }
    assert "create_initial_workspace_setup" in {tool.name for tool in setup_tools}


def test_enterprise_facade_tools_return_standard_payloads():
    home_result = prepare_home_dashboard_update.invoke(
        {
            "summary": "Focus sul setup iniziale.",
            "priorities": ["Validare cliente"],
            "risks": [],
            "next_actions": ["Creare progetto solo dopo conferma"],
        }
    )
    assert '"status": "prepared"' in home_result
    assert '"entity_type": "home_dashboard"' in home_result

    client_result = manage_client_record.invoke(
        {
            "operation": "inspect",
            "name": "Cliente che non esiste",
        }
    )
    assert '"entity_type": "client"' in client_result

    setup_result = validate_initial_workspace_setup.invoke(
        {
            "client_name": "Cliente Enterprise",
            "project_name": "Assessment Iniziale",
            "reason": "Test validation only",
        }
    )
    assert '"action": "validate_initial_workspace_setup"' in setup_result
