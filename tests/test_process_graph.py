from backend.graphs.process.graph import parse_process_router_json
from backend.graphs.process.skills_manifest import required_skills_for
from backend.graphs.process.state import ProcessState
from backend.graphs.process.subgraphs.discovery.state import ProcessDiscoveryState
from backend.graphs.process.subgraphs.discovery.tools import assess_discovery_readiness, discovery_tools
from backend.graphs.process.subgraphs.evidence.tools import (
    extract_process_claims,
    evidence_tools,
    prepare_evidence_coverage_matrix,
)
from backend.graphs.process.subgraphs.modeling.tools import (
    modeling_tools,
    validate_process_understanding_readiness,
)
from backend.graphs.process.tools import (
    get_process_semantic_context,
    get_process_workspace_brief,
    prepare_canvas_handoff,
    process_tools,
)
import backend.graphs.process.tools as process_tools_module
from backend.toolsets.process_memory import (
    index_process_evidence_graph,
    manage_process_evidence,
    retrieve_process_graph_context,
)
import backend.toolsets.process_memory as process_memory_module


def test_parse_process_router_json_returns_structured_state():
    result = parse_process_router_json(
        """
        {
          "route": "evidence",
          "confidence": 0.88,
          "needs_clarification": false,
          "clarification_question": null,
          "entity_hints": {"process": "proc-1", "source": "intervista ops"},
          "process_mode": "evidence",
          "process_objective": "extract process claims",
          "expected_result": "claim synthesis",
          "reason": "The request is about evidence from one source"
        }
        """,
        user_request="estrai i claim da questa intervista",
    )

    assert result["process_route"] == "evidence"
    assert result["process_mode"] == "evidence"
    assert result["process_objective"] == "extract process claims"
    assert result["delegation_target"] == "evidence_subgraph"
    assert result["routing_confidence"] == 0.88
    assert result["entity_hints"] == {"process": "proc-1", "source": "intervista ops"}
    assert result["delegation_payload"]["expected_result"] == "claim synthesis"
    assert result["routing_trace"][0]["route"] == "evidence"
    assert result["delegation_events"][0]["target"] == "evidence_subgraph"


def test_parse_process_router_json_falls_back_to_direct_for_invalid_route():
    result = parse_process_router_json('{"route":"unknown","confidence":5}')

    assert result["process_route"] == "direct"
    assert result["delegation_target"] is None
    assert result["routing_confidence"] == 1.0


def test_process_states_define_orchestration_fields():
    assert "process_route" in ProcessState.__annotations__
    assert "routing_trace" in ProcessState.__annotations__
    assert "process_claims" in ProcessState.__annotations__
    assert "discovery_facts" in ProcessDiscoveryState.__annotations__


def test_process_toolsets_are_small_and_owned():
    assert len(process_tools) <= 8
    assert len(discovery_tools) <= 8
    assert len(evidence_tools) <= 8
    assert len(modeling_tools) <= 8

    assert {tool.name for tool in process_tools} == {
        "get_process_workspace_brief",
        "get_process_semantic_context",
        "prepare_process_delegation_payload",
        "manage_process_evidence",
        "retrieve_process_graph_context",
        "retrieve_process_gap_context",
        "prepare_canvas_handoff",
    }
    assert "assess_discovery_readiness" in {tool.name for tool in discovery_tools}
    assert "manage_process_evidence" in {tool.name for tool in evidence_tools}
    assert "extract_process_claims" in {tool.name for tool in evidence_tools}
    assert "prepare_process_understanding_review" in {tool.name for tool in modeling_tools}


def test_process_skills_manifest_declares_required_skills():
    assert "process_macro_orchestration" in required_skills_for("process_macro")
    assert "evidence_synthesis" in required_skills_for("evidence_subgraph")
    assert "process_modeling" in required_skills_for("modeling_subgraph")


def test_process_facade_tools_return_standard_payloads(monkeypatch):
    process = {
        "id": "proc-1",
        "project_id": "project-1",
        "bpmn_model_id": "proc-1-bpmn",
        "name": "Order to Cash",
        "stage": "AS-IS",
        "status": "Bozza",
        "owner": "Ops",
        "readiness": 35,
    }
    review = {
        "bpmn_model_id": "proc-1-bpmn",
        "process_id": "proc-1",
        "source_text": "Cliente invia ordine. Ops verifica. Fattura emessa.",
        "process_understanding": {
            "schema_version": "process_understanding.v1",
            "language": "it",
            "title": "Order to Cash",
            "steps": [
                {"id": "Task_1", "label": "Ricevi ordine", "type": "user_task"},
                {"id": "Task_2", "label": "Verifica ordine", "type": "user_task"},
            ],
            "sequence": ["Task_1", "Task_2"],
            "unknowns": [],
        },
        "bpmn_semantic_model": {
            "id": "Process_proc_1",
            "name": "Order to Cash",
            "flowNodes": [
                {"id": "StartEvent_1", "type": "startEvent", "name": "Start"},
                {"id": "Task_1", "type": "userTask", "name": "Ricevi ordine"},
                {"id": "EndEvent_1", "type": "endEvent", "name": "End"},
            ],
            "sequenceFlows": [
                {"id": "Flow_1", "sourceRef": "StartEvent_1", "targetRef": "Task_1"},
                {"id": "Flow_2", "sourceRef": "Task_1", "targetRef": "EndEvent_1"},
            ],
        },
        "bpmn_brief": "## Order to Cash",
        "readiness_score": 8,
        "missing_information": [],
    }
    saved_sources = []

    monkeypatch.setattr(process_tools_module.workspace_database, "get_process", lambda process_id: process)
    monkeypatch.setattr(
        process_tools_module.workspace_database,
        "get_project",
        lambda project_id: {"id": project_id, "name": "ERP Assessment", "client": "Cliente Test"},
    )
    monkeypatch.setattr(
        process_tools_module.workspace_database,
        "get_bpmn_model",
        lambda bpmn_model_id: {
            "id": bpmn_model_id,
            "process_id": "proc-1",
            "name": "Order to Cash BPMN",
            "xml": None,
        },
    )
    monkeypatch.setattr(process_tools_module.workspace_database, "get_bpmn_review", lambda bpmn_model_id: review)
    monkeypatch.setattr(
        process_tools_module.workspace_database,
        "list_project_sources",
        lambda project_id: [
            {"id": "src-1", "project_id": project_id, "process_id": "proc-1", "name": "Interview Ops"}
        ],
    )
    monkeypatch.setattr(
        process_tools_module.workspace_database,
        "list_project_decisions",
        lambda project_id: [
            {"id": "dec-1", "project_id": project_id, "process_id": "proc-1", "title": "Soglia ordine"}
        ],
    )

    def fake_create_project_source(**kwargs):
        saved_sources.append(kwargs)
        return {
            "id": "src-2",
            "project_id": kwargs["project_id"],
            "process_id": kwargs["process_id"],
            "name": kwargs["name"],
            "type": kwargs["type"],
            "meta": kwargs["meta"],
        }

    monkeypatch.setattr(process_tools_module.workspace_database, "create_project_source", fake_create_project_source)

    brief = get_process_workspace_brief.invoke({"process_id": "proc-1"})
    assert '"action": "get_process_workspace_brief"' in brief
    assert '"source_count": 1' in brief

    semantic = get_process_semantic_context.invoke({"process_id": "proc-1"})
    assert '"action": "get_process_semantic_context"' in semantic
    assert '"readiness_score": 8' in semantic

    monkeypatch.setattr(process_memory_module.workspace_database, "get_process", lambda process_id: process)
    interview = manage_process_evidence.invoke(
        {
            "operation": "save_interview",
            "project_id": "project-1",
            "process_id": "proc-1",
            "title": "Interview Finance",
            "raw_content": "Finance confirms invoice emission after order validation.",
            "summary": "Finance confirms invoice emission after order validation.",
            "participants": ["Finance Manager"],
            "entities": ["Finance", "Invoice", "Order validation"],
            "claims": [
                {
                    "claim": "Finance emits invoice after order validation.",
                    "process_area": "activity",
                    "source_name": "Interview Finance",
                    "confidence": "high",
                    "status": "confirmed",
                    "linked_element_hint": "Emit invoice",
                }
            ],
            "relationships": [
                {
                    "source": "source:Interview Finance",
                    "relation": "CLAIM_SUPPORTS_ACTIVITY",
                    "target": "activity:Emit invoice",
                    "evidence": "Finance confirms invoice emission after order validation.",
                    "confidence": 0.9,
                    "confirmed": True,
                }
            ],
        }
    )
    assert '"action": "manage_process_evidence"' in interview
    assert '"entity_type": "process_interview"' in interview
    assert '"knowledge_graph_index": {' in interview

    indexed = index_process_evidence_graph.invoke(
        {
            "project_id": "project-1",
            "process_id": "proc-1",
            "source_title": "Interview Ops",
            "reason": "Evidence supports order validation.",
            "entities": ["Order to Cash", "Ops", "Verifica ordine"],
            "relationships": [
                {
                    "source": "source:Interview Ops",
                    "relation": "CLAIM_SUPPORTS_ACTIVITY",
                    "target": "activity:Verifica ordine",
                    "evidence": "Ops validates the order before invoicing.",
                    "confidence": 0.9,
                    "confirmed": True,
                }
            ],
        }
    )
    assert '"action": "index_process_evidence_graph"' in indexed

    graph_context = retrieve_process_graph_context.invoke(
        {
            "project_id": "project-1",
            "process_id": "proc-1",
            "query": "quali claim supportano la verifica ordine?",
            "reason": "Need evidence lineage for modeling.",
            "relation_focus": "claim-to-activity",
            "entities": ["Verifica ordine"],
        }
    )
    assert '"action": "retrieve_process_graph_context"' in graph_context
    assert "CLAIM_SUPPORTS_ACTIVITY" in graph_context

    handoff = prepare_canvas_handoff.invoke(
        {
            "process_id": "proc-1",
            "objective": "Generate canvas from semantic model.",
            "readiness_summary": "Review is ready.",
            "requested_canvas_action": "generate_from_semantic_model",
        }
    )
    assert '"target_owner": "canvas_macro"' in handoff


def test_process_subagent_tools_prepare_gate_payloads():
    discovery = assess_discovery_readiness.invoke(
        {
            "process_id": "proc-1",
            "scope_boundaries_clear": True,
            "main_actors_identified": True,
            "activities_supported": True,
            "decisions_and_handoffs_known": True,
            "exceptions_acknowledged": False,
            "contradictions_documented": True,
            "remaining_gaps_explicit": True,
        }
    )
    assert '"action": "assess_discovery_readiness"' in discovery
    assert '"status": "ready_for_modeling"' in discovery

    claims = extract_process_claims.invoke(
        {
            "process_id": "proc-1",
            "source_name": "Interview Ops",
            "claims": [
                {
                    "claim": "Ops validates the order before invoicing.",
                    "process_area": "activity",
                    "source_name": "Interview Ops",
                    "confidence": "high",
                    "status": "confirmed",
                    "linked_element_hint": "Verifica ordine",
                }
            ],
        }
    )
    assert '"entity_type": "process_claims"' in claims
    assert '"graph_rag_ready": true' in claims

    coverage = prepare_evidence_coverage_matrix.invoke(
        {
            "process_id": "proc-1",
            "coverage_items": [
                {
                    "process_area": "activity",
                    "coverage": "good",
                    "supporting_sources": ["Interview Ops"],
                    "gaps": [],
                }
            ],
            "modeling_blockers": [],
        }
    )
    assert '"action": "prepare_evidence_coverage_matrix"' in coverage


def test_modeling_readiness_reports_missing_review(monkeypatch):
    process = {
        "id": "proc-1",
        "project_id": "project-1",
        "bpmn_model_id": "proc-1-bpmn",
        "name": "Order to Cash",
        "stage": "AS-IS",
        "status": "Bozza",
        "owner": "Ops",
        "readiness": 35,
    }
    monkeypatch.setattr(process_tools_module.workspace_database, "get_process", lambda process_id: process)
    monkeypatch.setattr(process_tools_module.workspace_database, "get_project", lambda project_id: None)
    monkeypatch.setattr(
        process_tools_module.workspace_database,
        "get_bpmn_model",
        lambda bpmn_model_id: {"id": bpmn_model_id, "process_id": "proc-1", "name": "BPMN", "xml": None},
    )
    monkeypatch.setattr(process_tools_module.workspace_database, "get_bpmn_review", lambda bpmn_model_id: None)
    monkeypatch.setattr(process_tools_module.workspace_database, "list_project_sources", lambda project_id: [])
    monkeypatch.setattr(process_tools_module.workspace_database, "list_project_decisions", lambda project_id: [])

    result = validate_process_understanding_readiness.invoke(
        {
            "process_id": "proc-1",
            "objective": "Check if canvas handoff is possible.",
        }
    )

    assert '"status": "review_required"' in result
    assert "No valid ProcessUnderstanding review exists." in result
