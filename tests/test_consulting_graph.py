from backend.graphs.consulting.graph import parse_router_json
from backend.graphs.consulting.skills_manifest import required_skills_for
from backend.graphs.consulting.subgraphs.clients.tools import clients_tools
from backend.graphs.consulting.subgraphs.clients.state import ClientsState
from backend.graphs.consulting.subgraphs.home.tools import home_tools
from backend.graphs.consulting.subgraphs.home.state import HomeState
from backend.graphs.consulting.subgraphs.setup.tools import setup_tools
from backend.graphs.consulting.subgraphs.setup.state import SetupState
from backend.graphs.consulting.tools import consultant_tools
from backend.memory.models import (
    ConsultantSemanticMemory,
    ConsultingGraphRetrievalRequest,
    EpisodeMemory,
    episode_memory_to_mem0_content,
    semantic_memory_to_mem0_content,
)
from backend.memory.semantic import semantic_store
from backend.toolsets.memory import (
    manage_consultant_memory,
    manage_consulting_evidence,
    memory_tools,
    retrieve_consulting_context,
    retrieve_consulting_graph_context,
)
import backend.toolsets.memory as memory_module
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

    assert result["consulting_route"] == "clarification"
    assert result["delegation_target"] is None
    assert result["routing_confidence"] == 0.0
    assert result["needs_clarification"] is True
    assert result["orchestration_status"] == "invalid_structured_decision"


def test_consulting_router_refuses_unregistered_capability():
    result = parse_router_json(
        """
        {
          "route": "delegate_project",
          "confidence": 0.8,
          "suggested_capability": "consultant.run_any_tool",
          "reason": "Bad capability"
        }
        """
    )

    assert result["consulting_route"] == "clarification"
    assert result["delegation_events"] == []
    assert result["orchestration_status"] == "unregistered_capability"
    assert "Capability is not registered" in result["blocking_conditions"][-1]


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


def test_consulting_skills_manifest_declares_required_skills():
    assert "consult_macro_orchestration" in required_skills_for("consult_macro")
    assert "workspace_status_synthesis" in required_skills_for("home_subgraph")


def test_memory_models_format_entity_rich_mem0_content():
    semantic = ConsultantSemanticMemory(
        category="positioning",
        entity_names=["Sohay", "DeliR"],
        statement="Sohay positions DeliR as a consulting operating system.",
        confidence=0.9,
        source="test",
        durability="profile",
    )
    semantic_content = semantic_memory_to_mem0_content(semantic)
    assert "entities: Sohay, DeliR" in semantic_content
    assert "durability: profile" in semantic_content

    episode = EpisodeMemory(
        episode_type="decision",
        title="Scope decision",
        raw_content="We decided Consulting delegates BPMN to Canvas.",
        insights=["Consulting should not edit BPMN XML"],
        participants=["Sohay"],
        tags=["consulting", "delegation"],
    )
    episode_content = episode_memory_to_mem0_content(
        memory=episode,
        episode_id="ep-1",
        source_id="src-1",
        source_path="source.md",
    )
    assert "episode_id: ep-1" in episode_content
    assert "insights: Consulting should not edit BPMN XML" in episode_content


def test_retrieve_consulting_context_facade_returns_scoped_sections():
    result = retrieve_consulting_context.invoke(
        {
            "query": "metodo di delivery",
            "retrieval_scope": "semantic",
            "category": "delivery_method",
            "reason": "Need consultant method context.",
        }
    )
    assert "CONSULTING CONTEXT RETRIEVAL" in result
    assert "SEMANTIC MEMORY" in result


def test_graph_retrieval_tool_is_explicit_and_consulting_owned():
    tool_names = {tool.name for tool in consultant_tools}

    assert "retrieve_consulting_graph_context" in tool_names
    assert "manage_consultant_memory" in tool_names
    assert "search_consultant_memory" not in tool_names
    assert "forget_consultant_memory" not in tool_names
    assert "forget_consultant_memory" not in {tool.name for tool in memory_tools}
    assert len(consultant_tools) <= 8

    request = ConsultingGraphRetrievalRequest(
        query="Quali progetti sono collegati alle decisioni di delivery?",
        entities=["DeliR", "delivery"],
        relation_focus="project-to-decision",
        reason="Need relation-heavy consulting synthesis.",
        include_workspace_overview=False,
    )
    assert request.relation_focus == "project-to-decision"


def test_semantic_store_routes_to_mem0_mcp_only(monkeypatch):
    calls = []

    def fake_add_memory(**kwargs):
        calls.append(("add_memory", kwargs))
        return {"event_id": "evt-1"}

    def fake_search_memories(**kwargs):
        calls.append(("search_memories", kwargs))
        return {"results": [{"id": "mem-1", "memory": "DeliR usa Mem0 MCP."}]}

    def fake_delete_memory(**kwargs):
        calls.append(("delete_memory", kwargs))
        return {"deleted": True}

    monkeypatch.setattr(semantic_store.settings, "mem0_user_id", "test-user")
    monkeypatch.setattr(semantic_store.mem0_mcp_client, "add_memory", fake_add_memory)
    monkeypatch.setattr(semantic_store.mem0_mcp_client, "search_memories", fake_search_memories)
    monkeypatch.setattr(semantic_store.mem0_mcp_client, "delete_memory", fake_delete_memory)

    save_result = semantic_store.add_mem0_memory("stable fact")
    search_result = semantic_store.search_consultant_memory("MCP", category="architecture")
    delete_result = semantic_store.delete_consultant_memory("mem-1")

    assert save_result == "Memoria salvata in Mem0 MCP. [event_id: evt-1]"
    assert "DeliR usa Mem0 MCP." in search_result
    assert delete_result == "Memoria Mem0 MCP eliminata: mem-1."
    assert calls == [
        (
            "add_memory",
            {
                "text": "stable fact",
                "user_id": "test-user",
                "metadata": {"source": "delir"},
            },
        ),
        (
            "search_memories",
            {
                "query": "[architecture] MCP",
                "filters": {"AND": [{"user_id": "test-user"}]},
                "limit": 5,
            },
        ),
        ("delete_memory", {"memory_id": "mem-1"}),
    ]
    assert not hasattr(semantic_store, "get_memory_client")


def test_manage_consultant_memory_facade_routes_mcp_management_tools(monkeypatch):
    calls = []

    def fake_get_mem0_memory(memory_id):
        calls.append(("get_memory", memory_id))
        return {"id": memory_id, "memory": "Existing memory"}

    def fake_update_mem0_memory(memory_id, text=None, metadata=None):
        calls.append(("update_memory", memory_id, text, metadata))
        return {"id": memory_id, "memory": text, "metadata": metadata}

    def fake_delete_consultant_memory(memory_id):
        calls.append(("delete_memory", memory_id))
        return f"Memoria Mem0 MCP eliminata: {memory_id}."

    monkeypatch.setattr(memory_module.semantic_store, "get_mem0_memory", fake_get_mem0_memory)
    monkeypatch.setattr(memory_module.semantic_store, "update_mem0_memory", fake_update_mem0_memory)
    monkeypatch.setattr(memory_module.semantic_store, "delete_consultant_memory", fake_delete_consultant_memory)

    inspected = manage_consultant_memory.invoke(
        {
            "operation": "get_memory",
            "memory_id": "mem-1",
        }
    )
    blocked_update = manage_consultant_memory.invoke(
        {
            "operation": "update_memory",
            "memory_id": "mem-1",
            "text": "Updated memory",
        }
    )
    updated = manage_consultant_memory.invoke(
        {
            "operation": "update_memory",
            "memory_id": "mem-1",
            "text": "Updated memory",
            "metadata": {"category": "architecture"},
            "confirm_memory_id": True,
        }
    )
    deleted = manage_consultant_memory.invoke(
        {
            "operation": "delete_memory",
            "memory_id": "mem-1",
            "confirm_memory_id": True,
        }
    )

    assert '"operation": "get_memory"' in inspected
    assert "update_memory bloccato" in blocked_update
    assert '"operation": "update_memory"' in updated
    assert '"operation": "delete_memory"' in deleted
    assert calls == [
        ("get_memory", "mem-1"),
        ("update_memory", "mem-1", "Updated memory", {"category": "architecture"}),
        ("delete_memory", "mem-1"),
    ]


def test_manage_consultant_memory_blocks_bulk_delete_without_exact_confirmation():
    result = manage_consultant_memory.invoke(
        {
            "operation": "delete_all_memories",
            "confirm_destructive_action": True,
            "destructive_confirmation_text": "delete",
        }
    )

    assert "delete_all_memories bloccato" in result
    assert '"status": "blocked"' in result


def test_consulting_uses_manage_evidence_facade(monkeypatch):
    tool_names = {tool.name for tool in consultant_tools}
    saved_payloads = []

    assert "manage_consulting_evidence" in tool_names
    assert "save_episode" not in tool_names

    def fake_save_episode_memory(**kwargs):
        saved_payloads.append(kwargs)
        return "Episodio salvato: test [episode_id: ep-1] [source_id: src-1]."

    monkeypatch.setattr(memory_module.episodic_store, "save_episode_memory", fake_save_episode_memory)

    result = manage_consulting_evidence.invoke(
        {
            "operation": "save_interview",
            "title": "Intervista discovery",
            "raw_content": "Il cliente descrive il problema.",
            "summary": "Problema descritto dal cliente.",
            "participants": ["Cliente"],
            "project": "project-1",
        }
    )

    assert '"action": "manage_consulting_evidence"' in result
    assert '"entity_type": "consulting_interview"' in result
    assert saved_payloads[-1]["episode_type"] == "interview"


def test_retrieve_consulting_graph_context_returns_grounded_sections():
    result = retrieve_consulting_graph_context.invoke(
        {
            "query": "Quali insight sono collegati alle decisioni?",
            "entities": ["DeliR"],
            "relation_focus": "insight-to-decision",
            "reason": "Need graph-style context.",
            "include_workspace_overview": False,
        }
    )

    assert "CONSULTING GRAPH CONTEXT RETRIEVAL" in result
    assert "MEM0 RELATIONAL MEMORY" in result
    assert "EPISODIC EVIDENCE LINKS" in result
    assert "Use workspace DB records as authoritative operational state" in result
