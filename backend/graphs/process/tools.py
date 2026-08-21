import json
from typing import Literal

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from backend import workspace_database
from backend.bpmn_semantic import BPMNSemanticModel
from backend.process_understanding import ProcessUnderstanding, render_process_review
from backend.toolsets.process_memory import (
    retrieve_process_gap_context,
    retrieve_process_graph_context,
    save_process_episode,
    save_process_interview,
)
from backend.toolsets.workspace import enterprise_tool_result


ProcessTargetOwner = Literal[
    "process_macro",
    "discovery_subgraph",
    "evidence_subgraph",
    "modeling_subgraph",
    "analysis_subgraph",
    "redesign_subgraph",
    "canvas_macro",
]


class ProcessDelegationPayloadInput(BaseModel):
    target_owner: ProcessTargetOwner = Field(description="Destination owner for the next narrow process task.")
    user_request: str = Field(description="Latest user request being delegated.")
    expected_result: str = Field(description="Concrete output expected from the receiving owner.")
    reason: str = Field(description="Why this owner is responsible.")
    known_context: str = Field(default="", description="Minimal process facts, ids, gaps, or review state needed.")


class ProcessEvidenceInput(BaseModel):
    process_id: str = Field(description="Current process id.")
    name: str = Field(description="Human-readable source name, e.g. 'Interview Ops 2026-08-20'.")
    evidence_type: Literal[
        "interview_notes",
        "workshop_notes",
        "document",
        "system_export",
        "observation",
        "example_case",
        "other",
    ] = Field(description="Kind of evidence being saved.")
    summary: str = Field(description="Concise evidence summary. Do not include secrets or raw sensitive data.")
    provenance_note: str = Field(default="", description="Where this came from, when known.")
    confidence: Literal["low", "medium", "high", "unknown"] = Field(
        default="medium",
        description="Reliability of this evidence item before synthesis.",
    )
    tags: list[str] = Field(default_factory=list, description="Process areas touched by this evidence.")


class ProcessGraphContextRequestInput(BaseModel):
    process_id: str = Field(description="Current process id.")
    query: str = Field(description="Question that future process GraphRAG should answer.")
    reason: str = Field(description="Why relation-heavy retrieval would help.")
    entity_hints: list[str] = Field(
        default_factory=list,
        description="Known process entities: actor, activity, decision, handoff, document, system, source, gap.",
    )
    relation_focus: Literal[
        "source-to-claim",
        "claim-to-activity",
        "actor-to-handoff",
        "decision-to-path",
        "gap-to-modeling",
        "contradiction",
        "canvas-mapping",
        "general",
    ] = "general"


class CanvasHandoffInput(BaseModel):
    process_id: str = Field(description="Current process id.")
    objective: str = Field(description="What Canvas Macro should do next.")
    readiness_summary: str = Field(description="Why this process is or is not ready for canvas work.")
    unresolved_gaps: list[str] = Field(default_factory=list, description="Gaps Canvas must preserve as notes.")
    constraints: list[str] = Field(default_factory=list, description="Modeling constraints or user requirements.")
    requested_canvas_action: Literal[
        "inspect_existing_xml",
        "generate_from_semantic_model",
        "layout",
        "validate",
        "targeted_edit",
        "replace_xml",
    ] = Field(description="Specific Canvas Macro action requested.")


def _filter_process_items(items: list[dict], process_id: str) -> list[dict]:
    return [item for item in items if item.get("process_id") in {None, process_id}]


def process_workspace_payload(process_id: str) -> dict:
    process = workspace_database.get_process(process_id)
    if process is None:
        raise ValueError(f"Processo non trovato: {process_id}")

    project = workspace_database.get_project(process["project_id"])
    bpmn_model = workspace_database.get_bpmn_model(process["bpmn_model_id"])
    review = workspace_database.get_bpmn_review(process["bpmn_model_id"])
    project_sources = workspace_database.list_project_sources(process["project_id"])
    project_decisions = workspace_database.list_project_decisions(process["project_id"])

    return {
        "process": process,
        "project": project,
        "bpmn_model": {
            "id": bpmn_model["id"],
            "process_id": bpmn_model["process_id"],
            "name": bpmn_model["name"],
            "has_xml": bool(bpmn_model["xml"]),
        }
        if bpmn_model
        else None,
        "review": review,
        "sources": _filter_process_items(project_sources, process_id),
        "decisions": _filter_process_items(project_decisions, process_id),
    }


def process_understanding_from_payload(payload: dict) -> ProcessUnderstanding | None:
    review = payload.get("review") or {}
    raw = review.get("process_understanding")
    if not raw:
        return None

    try:
        return ProcessUnderstanding.model_validate(raw)
    except Exception:
        return None


def bpmn_semantic_model_from_payload(payload: dict) -> BPMNSemanticModel | None:
    review = payload.get("review") or {}
    raw = review.get("bpmn_semantic_model")
    if not raw:
        return None

    try:
        return BPMNSemanticModel.model_validate(raw)
    except Exception:
        return None


@tool
def get_process_workspace_brief(process_id: str) -> str:
    """
    Read the authoritative process workspace brief: process record, project,
    linked process/project evidence, open decisions, BPMN model metadata and
    pending review status. Use before routing process work or answering from context.
    """
    payload = process_workspace_payload(process_id)
    process = payload["process"]
    review = payload["review"]

    return enterprise_tool_result(
        status="ok",
        action="get_process_workspace_brief",
        entity_type="process",
        entity_id=process_id,
        summary=f"{process['name']} - {process['stage']} - readiness {process['readiness']}%",
        payload={
            "process": process,
            "project": payload["project"],
            "bpmn_model": payload["bpmn_model"],
            "source_count": len(payload["sources"]),
            "decision_count": len(payload["decisions"]),
            "sources": payload["sources"],
            "decisions": payload["decisions"],
            "review_pending": review is not None,
            "review_readiness_score": review.get("readiness_score") if review else None,
            "review_missing_information": review.get("missing_information") if review else [],
        },
    )


@tool
def get_process_semantic_context(process_id: str) -> str:
    """
    Read the current ProcessUnderstanding and BPMNSemanticModel context for one
    process. Use before discovery, evidence synthesis, modeling, analysis or
    canvas handoff so the user does not need to repeat already captured context.
    """
    payload = process_workspace_payload(process_id)
    process = payload["process"]
    review = payload["review"]
    understanding = process_understanding_from_payload(payload)
    semantic_model = bpmn_semantic_model_from_payload(payload)

    return enterprise_tool_result(
        status="ok" if review else "missing",
        action="get_process_semantic_context",
        entity_type="process_semantic_context",
        entity_id=process_id,
        summary=(
            f"Semantic context available for {process['name']}."
            if review
            else f"No ProcessUnderstanding review exists yet for {process['name']}."
        ),
        payload={
            "process": process,
            "process_understanding": understanding.model_dump(mode="json") if understanding else None,
            "process_review_markdown": render_process_review(understanding) if understanding else "",
            "bpmn_semantic_model": semantic_model.model_dump(mode="json") if semantic_model else None,
            "readiness_score": review.get("readiness_score") if review else None,
            "missing_information": review.get("missing_information") if review else [],
            "model_warnings": semantic_model.model_warnings if semantic_model else [],
        },
        warnings=[] if review else ["Run discovery/evidence/modeling before canvas generation."],
    )


@tool(args_schema=ProcessDelegationPayloadInput)
def prepare_process_delegation_payload(
    target_owner: ProcessTargetOwner,
    user_request: str,
    expected_result: str,
    reason: str,
    known_context: str = "",
) -> str:
    """
    Purpose: create a narrow handoff from Process Macro to a process subgraph or
    Canvas Macro. This does not execute the work and does not mutate records.
    """
    return enterprise_tool_result(
        status="prepared",
        action="prepare_process_delegation_payload",
        entity_type="process_delegation",
        summary=expected_result,
        payload={
            "target_owner": target_owner,
            "user_request": user_request,
            "expected_result": expected_result,
            "reason": reason,
            "known_context": known_context,
        },
    )


@tool(args_schema=ProcessEvidenceInput)
def save_process_evidence(
    process_id: str,
    name: str,
    evidence_type: str,
    summary: str,
    provenance_note: str = "",
    confidence: str = "medium",
    tags: list[str] | None = None,
) -> str:
    """
    Save a process-scoped evidence source as a WorkspaceSource. Use only for real
    interview notes, workshop notes, documents, observations or examples that
    should remain linked to this process. This is not GraphRAG indexing yet.
    """
    process = workspace_database.get_process(process_id)
    if process is None:
        raise ValueError(f"Processo non trovato: {process_id}")

    meta = json.dumps(
        {
            "summary": summary,
            "provenance_note": provenance_note,
            "confidence": confidence,
            "tags": tags or [],
            "graph_rag_indexed": False,
        },
        ensure_ascii=False,
    )
    source = workspace_database.create_project_source(
        project_id=process["project_id"],
        process_id=process_id,
        name=name,
        type=evidence_type,
        meta=meta,
    )
    return enterprise_tool_result(
        status="created",
        action="save_process_evidence",
        entity_type="process_evidence",
        entity_id=source["id"],
        summary=f"Evidence saved for process {process['name']}: {name}",
        payload={
            "source": source,
            "process_id": process_id,
            "project_id": process["project_id"],
            "graph_rag_indexed": False,
        },
        next_actions=[
            {
                "owner": "evidence_subgraph",
                "action": "Synthesize claims, confidence, contradictions and open questions from this source.",
            }
        ],
    )


@tool(args_schema=ProcessGraphContextRequestInput)
def prepare_process_graph_context_request(
    process_id: str,
    query: str,
    reason: str,
    entity_hints: list[str] | None = None,
    relation_focus: str = "general",
) -> str:
    """
    Prepare the future process GraphRAG retrieval request without performing
    retrieval. Use when relation-heavy process memory would help, but GraphRAG is
    not enabled yet. The output should be used as a planning artifact only.
    """
    payload = process_workspace_payload(process_id)
    return enterprise_tool_result(
        status="not_configured",
        action="prepare_process_graph_context_request",
        entity_type="process_graph_context_request",
        entity_id=process_id,
        summary="Process GraphRAG is not enabled yet; retrieval request prepared.",
        payload={
            "process": payload["process"],
            "query": query,
            "reason": reason,
            "entity_hints": entity_hints or [],
            "relation_focus": relation_focus,
            "future_tool_slot": "retrieve_process_graph_context",
        },
        warnings=["Do not claim GraphRAG evidence was retrieved in this turn."],
    )


@tool(args_schema=CanvasHandoffInput)
def prepare_canvas_handoff(
    process_id: str,
    objective: str,
    readiness_summary: str,
    unresolved_gaps: list[str] | None = None,
    constraints: list[str] | None = None,
    requested_canvas_action: str = "generate_from_semantic_model",
) -> str:
    """
    Prepare a structured handoff to Canvas Macro. Use only after checking the
    current ProcessUnderstanding/BPMNSemanticModel. This does not edit XML.
    """
    payload = process_workspace_payload(process_id)
    process = payload["process"]
    review = payload["review"]
    semantic_model = bpmn_semantic_model_from_payload(payload)
    warnings = []

    if review is None:
        warnings.append("No ProcessUnderstanding review exists yet.")
    elif (review.get("readiness_score") or 0) < 7:
        warnings.append("Readiness score is below the recommended canvas threshold.")
    if semantic_model is None:
        warnings.append("No BPMNSemanticModel is available yet.")

    return enterprise_tool_result(
        status="prepared" if not warnings else "review_required",
        action="prepare_canvas_handoff",
        entity_type="canvas_handoff",
        entity_id=process_id,
        summary=objective,
        payload={
            "target_owner": "canvas_macro",
            "project_id": process["project_id"],
            "process_id": process_id,
            "bpmn_model_id": process["bpmn_model_id"],
            "process_name": process["name"],
            "requested_canvas_action": requested_canvas_action,
            "objective": objective,
            "readiness_summary": readiness_summary,
            "readiness_score": review.get("readiness_score") if review else None,
            "missing_information": review.get("missing_information") if review else [],
            "unresolved_gaps": unresolved_gaps or [],
            "constraints": constraints or [],
            "semantic_model_available": semantic_model is not None,
        },
        warnings=warnings,
    )


PROCESS_TOOL_POLICY = """
Process Macro tools.

The Process Macro Agent owns one process workspace. It orchestrates discovery,
evidence synthesis, ProcessUnderstanding, BPMN semantic readiness and handoff to
Canvas Macro. It can use the enterprise knowledge graph for relation-heavy
process evidence, gaps, contradictions and lineage. It does not directly edit
BPMN XML.
""".strip()


process_tools = [
    get_process_workspace_brief,
    get_process_semantic_context,
    prepare_process_delegation_payload,
    save_process_interview,
    save_process_episode,
    retrieve_process_graph_context,
    retrieve_process_gap_context,
    prepare_canvas_handoff,
]
