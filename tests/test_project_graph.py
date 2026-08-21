from backend.graphs.project.graph import parse_project_router_json
from backend.graphs.project.skills_manifest import required_skills_for
from backend.graphs.project.state import ProjectState
from backend.graphs.project.subgraphs.delivery.state import ProjectDeliveryState
from backend.graphs.project.subgraphs.delivery.tools import delivery_tools
from backend.graphs.project.subgraphs.process_coordination.state import (
    ProjectProcessCoordinationState,
)
from backend.graphs.project.subgraphs.process_coordination.tools import process_coordination_tools
from backend.graphs.project.tools import (
    get_project_workspace_brief,
    identify_cross_process_dependencies,
    prepare_project_status_update,
    prepare_process_handoff,
    project_tools,
)
import backend.graphs.project.tools as project_tools_module
from backend.toolsets.project_memory import (
    extract_project_graph_from_evidence,
    manage_project_evidence,
    retrieve_cross_process_impact_context,
    retrieve_project_graph_context,
    retrieve_project_gap_context,
)
import backend.toolsets.project_memory as project_memory_module


def test_parse_project_router_json_returns_structured_state():
    result = parse_project_router_json(
        """
        {
          "route": "process_coordination",
          "confidence": 0.91,
          "needs_clarification": false,
          "clarification_question": null,
          "entity_hints": {"project": "p1", "process": null},
          "project_mode": "coordination",
          "project_objective": "sequence project processes",
          "expected_result": "build process workplan",
          "reason": "The request spans multiple processes"
        }
        """,
        user_request="quali processi mappiamo prima?",
    )

    assert result["project_route"] == "process_coordination"
    assert result["project_mode"] == "coordination"
    assert result["project_objective"] == "sequence project processes"
    assert result["delegation_target"] == "process_coordination_subgraph"
    assert result["routing_confidence"] == 0.91
    assert result["entity_hints"] == {"project": "p1", "process": None}
    assert result["delegation_payload"]["expected_result"] == "build process workplan"
    assert result["routing_trace"][0]["route"] == "process_coordination"
    assert result["delegation_events"][0]["target"] == "process_coordination_subgraph"


def test_parse_project_router_json_falls_back_to_direct_for_invalid_route():
    result = parse_project_router_json('{"route":"unknown","confidence":5}')

    assert result["project_route"] == "clarification"
    assert result["delegation_target"] is None
    assert result["routing_confidence"] == 0.0
    assert result["needs_clarification"] is True
    assert result["orchestration_status"] == "invalid_structured_decision"


def test_project_router_requires_unambiguous_process_for_delegation():
    result = parse_project_router_json(
        """
        {
          "route": "delegate_process",
          "confidence": 0.83,
          "entity_hints": {"project": "project-1", "process": null},
          "goal": "MODEL_AS_IS",
          "intent": "process_engineering",
          "next_action": "DELEGATE_TO_PROCESS",
          "suggested_capability": "project.process_delegation",
          "reason": "Deep work on one process."
        }
        """,
        state={
            "project_processes": [
                {"id": "proc-1", "name": "Acquisti"},
                {"id": "proc-2", "name": "Vendite"},
            ]
        },
    )

    assert result["project_route"] == "clarification"
    assert result["delegation_events"] == []
    assert result["orchestration_status"] == "missing_prerequisite"
    assert "Missing prerequisite: unambiguous_process_target" in result["blocking_conditions"]


def test_project_states_separate_snapshot_from_append_fields():
    assert "project_processes" in ProjectState.__annotations__
    assert "routing_trace" in ProjectState.__annotations__
    assert "delivery_risks" in ProjectDeliveryState.__annotations__
    assert "cross_process_dependencies" in ProjectProcessCoordinationState.__annotations__


def test_project_toolsets_are_small_and_owned():
    assert len(project_tools) <= 8
    assert len(delivery_tools) <= 8
    assert len(process_coordination_tools) <= 8

    assert {tool.name for tool in project_tools} == {
        "get_project_workspace_brief",
        "prepare_project_delegation_payload",
        "manage_project_evidence",
        "extract_project_graph_from_evidence",
        "retrieve_project_graph_context",
        "retrieve_project_gap_context",
        "retrieve_cross_process_impact_context",
    }
    assert "prepare_project_status_update" in {tool.name for tool in delivery_tools}
    assert "prepare_process_handoff" in {tool.name for tool in process_coordination_tools}


def test_project_skills_manifest_declares_required_skills():
    assert "project_macro_orchestration" in required_skills_for("project_macro")
    assert "multi_process_coordination" in required_skills_for("process_coordination_subgraph")


def test_project_facade_tools_return_standard_payloads(monkeypatch):
    project = {
        "id": "project-1",
        "client_id": "client-1",
        "client": "Cliente Test",
        "name": "Enterprise Mapping",
        "phase": "Discovery",
        "status": "Attivo",
        "progress": 25,
        "processes": 2,
        "next_step": "Completare interviste iniziali",
        "milestones": ["Kickoff"],
        "open_issues": ["Validare perimetro"],
        "deliverables": ["Mappa AS-IS"],
        "process_items": [
            {
                "id": "proc-1",
                "project_id": "project-1",
                "bpmn_model_id": "proc-1-bpmn",
                "name": "Acquisti",
                "stage": "AS-IS",
                "status": "Bozza",
                "owner": "Ops",
                "readiness": 30,
            },
            {
                "id": "proc-2",
                "project_id": "project-1",
                "bpmn_model_id": "proc-2-bpmn",
                "name": "Vendite",
                "stage": "AS-IS",
                "status": "Bozza",
                "owner": "Sales",
                "readiness": 70,
            },
        ],
    }

    monkeypatch.setattr(project_tools_module.workspace_database, "get_project", lambda project_id: project)
    monkeypatch.setattr(
        project_tools_module.workspace_database,
        "list_project_sources",
        lambda project_id: [{"id": "src-1", "project_id": project_id, "name": "Intervista", "type": "Note", "meta": ""}],
    )
    monkeypatch.setattr(
        project_tools_module.workspace_database,
        "list_project_decisions",
        lambda project_id: [{"id": "dec-1", "project_id": project_id, "title": "Scope", "owner": "PM", "status": "Aperta"}],
    )
    monkeypatch.setattr(
        project_tools_module.workspace_database,
        "get_process",
        lambda process_id: {
            "id": process_id,
            "project_id": "project-1",
            "bpmn_model_id": f"{process_id}-bpmn",
            "name": "Acquisti",
            "stage": "AS-IS",
            "status": "Bozza",
            "owner": "Ops",
            "readiness": 30,
        },
    )

    brief = get_project_workspace_brief.invoke({"project_id": "project-1"})
    assert '"action": "get_project_workspace_brief"' in brief
    assert '"process_count": 2' in brief

    status_update = prepare_project_status_update.invoke(
        {
            "project_id": "project-1",
            "summary": "Discovery in corso.",
            "risks": ["Perimetro non validato"],
            "next_actions": ["Pianificare interviste"],
        }
    )
    assert '"entity_type": "project_delivery_update"' in status_update

    dependencies = identify_cross_process_dependencies.invoke(
        {
            "project_id": "project-1",
            "reason": "Capire ordine di mappatura.",
            "relationship_hints": ["Vendite genera input per Acquisti"],
        }
    )
    assert '"entity_type": "cross_process_dependencies"' in dependencies

    handoff = prepare_process_handoff.invoke(
        {
            "project_id": "project-1",
            "process_id": "proc-1",
            "expected_result": "Completare AS-IS Acquisti",
            "reason": "Readiness bassa",
        }
    )
    assert '"target_owner": "process_macro"' in handoff


def test_project_scoped_memory_tools_save_and_retrieve_evidence(monkeypatch):
    project = {
        "id": "project-1",
        "name": "Enterprise Mapping",
    }
    processes = [
        {"id": "proc-1", "project_id": "project-1"},
        {"id": "proc-2", "project_id": "project-1"},
    ]
    saved_payloads = []

    monkeypatch.setattr(project_memory_module.workspace_database, "get_project", lambda project_id: project)
    monkeypatch.setattr(
        project_memory_module.workspace_database,
        "list_project_processes",
        lambda project_id: processes,
    )

    def fake_save_episode_memory(**kwargs):
        saved_payloads.append(kwargs)
        return "Episodio salvato: test [episode_id: ep-1] [source_id: src-1]. Memoria salvata in Mem0."

    monkeypatch.setattr(
        project_memory_module.episodic_store,
        "save_episode_memory",
        fake_save_episode_memory,
    )
    monkeypatch.setattr(
        project_memory_module.episodic_store,
        "search_episode_memory",
        lambda **kwargs: "MEMORIA EPISODICA RECUPERATA.",
    )

    interview = manage_project_evidence.invoke(
        {
            "operation": "save_interview",
            "project_id": "project-1",
            "title": "Intervista Acquisti",
            "raw_content": "Il responsabile acquisti descrive il flusso.",
            "summary": "Flusso acquisti discusso.",
            "insights": ["Acquisti dipende dal budget"],
            "participants": ["Responsabile Acquisti"],
            "process_ids": ["proc-1", "missing-proc"],
            "entities": ["Acquisti", "Budget", "CFO"],
            "relationships": [
                {
                    "source": "process:Acquisti",
                    "relation": "DEPENDS_ON",
                    "target": "process:Budget",
                    "evidence": "Gli ordini richiedono centro di costo approvato.",
                    "confidence": 0.8,
                    "confirmed": False,
                }
            ],
            "gaps": [
                {
                    "title": "Soglia approvazione non chiara",
                    "missing_information": "Manca soglia economica per approvazione CFO.",
                    "affected_process_ids": ["proc-1", "missing-proc"],
                    "required_evidence": "Intervista CFO",
                    "severity": "high",
                }
            ],
            "roi_impacts": [
                {
                    "title": "Ritardo ordini",
                    "impact_area": "working_capital",
                    "affected_process_ids": ["proc-1"],
                    "mechanism": "Attese su budget bloccano emissione ordine.",
                    "evidence": "Dipendenza da centro di costo approvato.",
                    "confidence": 0.7,
                }
            ],
            "tags": ["acquisti"],
        }
    )

    assert '"action": "manage_project_evidence"' in interview
    assert '"entity_type": "project_interview"' in interview
    assert saved_payloads[-1]["project"] == "project-1"
    assert "project:project-1" in saved_payloads[-1]["tags"]
    assert "process:proc-1" in saved_payloads[-1]["tags"]
    assert "process:missing-proc" not in saved_payloads[-1]["tags"]
    assert "graph:relationships" in saved_payloads[-1]["tags"]
    assert "graph:gaps" in saved_payloads[-1]["tags"]
    assert "graph:roi" in saved_payloads[-1]["tags"]
    assert "PROJECT_GRAPH_INDEX" in saved_payloads[-1]["insights"][-1]
    assert "process:Acquisti DEPENDS_ON process:Budget" in saved_payloads[-1]["insights"][-1]

    episode = manage_project_evidence.invoke(
        {
            "operation": "save_episode",
            "project_id": "project-1",
            "episode_type": "workshop",
            "title": "Workshop kickoff",
            "raw_content": "Note workshop",
            "process_ids": ["proc-2"],
        }
    )
    assert '"action": "manage_project_evidence"' in episode
    assert "process:proc-2" in saved_payloads[-1]["tags"]

    extraction = extract_project_graph_from_evidence.invoke(
        {
            "project_id": "project-1",
            "raw_content": "Acquisti dipende da Budget.",
            "reason": "Preparare extraction enterprise.",
            "process_ids": ["proc-1", "missing-proc"],
            "relationships": [
                {
                    "source": "process:Acquisti",
                    "relation": "DEPENDS_ON",
                    "target": "process:Budget",
                    "evidence": "Acquisti dipende da Budget.",
                    "confidence": 0.8,
                    "confirmed": False,
                }
            ],
            "questions_to_validate": ["Chi conferma il centro di costo?"],
        }
    )
    assert '"action": "extract_project_graph_from_evidence"' in extraction
    assert "missing-proc" not in extraction


def test_project_graph_context_is_scoped_to_project(monkeypatch):
    project = {
        "id": "project-1",
        "name": "Enterprise Mapping",
    }
    processes = [
        {"id": "proc-1", "project_id": "project-1", "name": "Acquisti"},
        {"id": "proc-2", "project_id": "project-1", "name": "Budget"},
    ]

    monkeypatch.setattr(project_memory_module.workspace_database, "get_project", lambda project_id: project)
    monkeypatch.setattr(
        project_memory_module.workspace_database,
        "list_project_processes",
        lambda project_id: processes,
    )
    monkeypatch.setattr(
        project_memory_module.workspace_database,
        "list_project_sources",
        lambda project_id: [{"id": "src-1", "project_id": project_id, "name": "Intervista CFO"}],
    )
    monkeypatch.setattr(
        project_memory_module.workspace_database,
        "list_project_decisions",
        lambda project_id: [{"id": "dec-1", "project_id": project_id, "title": "Budget approval"}],
    )
    monkeypatch.setattr(
        project_memory_module.semantic_store,
        "search_consultant_memory",
        lambda **kwargs: f"MEM0 GRAPH RESULT: {kwargs['query']}",
    )
    monkeypatch.setattr(
        project_memory_module.episodic_store,
        "search_episode_memory",
        lambda **kwargs: f"EPISODIC RESULT project={kwargs['project']} query={kwargs['query']}",
    )

    result = retrieve_project_graph_context.invoke(
        {
            "project_id": "project-1",
            "query": "Acquisti dipende da Budget?",
            "relation_focus": "process-to-process",
            "reason": "Capire dipendenze tra processi.",
            "entities": ["Acquisti", "Budget"],
            "process_ids": ["proc-1", "missing-proc"],
        }
    )

    assert '"action": "retrieve_project_graph_context"' in result
    assert '"entity_type": "project_graph_context"' in result
    assert "project_id: project-1" in result
    assert "relation_focus: process-to-process" in result
    assert "EPISODIC RESULT project=project-1" in result
    assert "proc-1" in result
    assert "missing-proc" not in result

    gap_result = retrieve_project_gap_context.invoke(
        {
            "project_id": "project-1",
            "query": "quali dati mancano?",
            "process_id": "proc-1",
        }
    )
    assert "gap-and-inconsistency" in gap_result

    impact_result = retrieve_cross_process_impact_context.invoke(
        {
            "project_id": "project-1",
            "query": "impatto ROI dipendenze",
            "process_ids": ["proc-1", "proc-2"],
        }
    )
    assert "cross-process-impact-and-roi" in impact_result
