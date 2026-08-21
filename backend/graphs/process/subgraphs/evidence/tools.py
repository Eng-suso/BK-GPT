from typing import Literal

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from backend.graphs.process.tools import process_workspace_payload
from backend.toolsets.process_memory import (
    extract_process_graph_from_evidence,
    index_process_evidence_graph,
    manage_process_evidence,
)
from backend.toolsets.workspace import enterprise_tool_result


ProcessArea = Literal[
    "scope",
    "actor",
    "activity",
    "decision",
    "handoff",
    "system",
    "data",
    "exception",
    "control",
    "timing",
]


def _jsonable_items(items: list) -> list[dict]:
    return [
        item.model_dump(mode="json") if hasattr(item, "model_dump") else item
        for item in items
    ]


class ProcessClaim(BaseModel):
    claim: str = Field(description="Single process claim extracted from evidence.")
    process_area: ProcessArea = Field(description="Process area described by the claim.")
    source_name: str = Field(description="Source that supports or states this claim.")
    confidence: Literal["low", "medium", "high", "unknown"] = Field(description="Evidence confidence.")
    status: Literal["confirmed", "partial", "contradicted", "inferred", "unsupported"] = Field(
        description="Support status for this claim."
    )
    linked_element_hint: str | None = Field(
        default=None,
        description="Optional actor/activity/decision/handoff id or name this claim may map to.",
    )


class ExtractClaimsInput(BaseModel):
    process_id: str = Field(description="Current process id.")
    source_name: str = Field(description="Source being processed.")
    claims: list[ProcessClaim] = Field(description="Atomic process claims extracted from the source.")
    extraction_notes: list[str] = Field(default_factory=list, description="Notes about ambiguity or source quality.")


class EvidenceSynthesisInput(BaseModel):
    process_id: str = Field(description="Current process id.")
    source_list: list[str] = Field(description="Sources considered in this synthesis.")
    confirmed_claims: list[str] = Field(default_factory=list, description="Claims supported well enough to model.")
    hypotheses: list[str] = Field(default_factory=list, description="Claims plausible but not confirmed.")
    contradictions: list[str] = Field(default_factory=list, description="Conflicting claims or source disagreement.")
    open_questions: list[str] = Field(default_factory=list, description="Questions needed before modeling or validation.")
    recommended_next_evidence: list[str] = Field(default_factory=list, description="Sources to collect next.")


class ContradictionInput(BaseModel):
    process_id: str = Field(description="Current process id.")
    title: str = Field(description="Short contradiction title.")
    conflicting_claims: list[str] = Field(description="Claims that cannot all be true.")
    affected_process_area: ProcessArea = Field(description="Process area affected by the contradiction.")
    source_names: list[str] = Field(default_factory=list, description="Sources involved in the contradiction.")
    resolution_needed: str = Field(description="What must be checked to resolve it.")
    severity: Literal["low", "medium", "high", "blocking"] = "medium"


class CoverageItem(BaseModel):
    process_area: ProcessArea = Field(description="Process area being assessed.")
    coverage: Literal["none", "weak", "partial", "good"] = Field(description="Evidence coverage level.")
    supporting_sources: list[str] = Field(default_factory=list, description="Sources supporting this area.")
    gaps: list[str] = Field(default_factory=list, description="Missing evidence for this area.")


class EvidenceCoverageInput(BaseModel):
    process_id: str = Field(description="Current process id.")
    coverage_items: list[CoverageItem] = Field(description="Coverage by process area.")
    modeling_blockers: list[str] = Field(default_factory=list, description="Evidence gaps blocking modeling.")


@tool
def get_process_evidence_brief(process_id: str) -> str:
    """
    Read process sources, decisions and current review gaps for evidence
    synthesis. Use before extracting claims or assessing coverage.
    """
    payload = process_workspace_payload(process_id)
    return enterprise_tool_result(
        status="ok",
        action="get_process_evidence_brief",
        entity_type="process_evidence_brief",
        entity_id=process_id,
        summary=f"Evidence brief for {payload['process']['name']}",
        payload={
            "process": payload["process"],
            "sources": payload["sources"],
            "decisions": payload["decisions"],
            "missing_information": payload["review"].get("missing_information") if payload["review"] else [],
        },
    )


@tool(args_schema=ExtractClaimsInput)
def extract_process_claims(
    process_id: str,
    source_name: str,
    claims: list[dict],
    extraction_notes: list[str] | None = None,
) -> str:
    """
    Structure atomic process claims from one source. Use before synthesis or
    future GraphRAG indexing. Each claim must keep source, confidence and status.
    """
    claim_payload = _jsonable_items(claims)
    return enterprise_tool_result(
        status="prepared",
        action="extract_process_claims",
        entity_type="process_claims",
        entity_id=process_id,
        summary=f"{len(claim_payload)} claims extracted from {source_name}.",
        payload={
            "process_id": process_id,
            "source_name": source_name,
            "claims": claim_payload,
            "extraction_notes": extraction_notes or [],
            "graph_rag_ready": True,
        },
    )


@tool(args_schema=EvidenceSynthesisInput)
def synthesize_process_evidence(
    process_id: str,
    source_list: list[str],
    confirmed_claims: list[str] | None = None,
    hypotheses: list[str] | None = None,
    contradictions: list[str] | None = None,
    open_questions: list[str] | None = None,
    recommended_next_evidence: list[str] | None = None,
) -> str:
    """
    Produce the canonical evidence synthesis for one process. Use before
    modeling so the ProcessUnderstanding is based on evidence, not free text.
    """
    return enterprise_tool_result(
        status="prepared",
        action="synthesize_process_evidence",
        entity_type="process_evidence_synthesis",
        entity_id=process_id,
        summary=f"Evidence synthesis from {len(source_list)} sources.",
        payload={
            "process_id": process_id,
            "source_list": source_list,
            "confirmed_claims": confirmed_claims or [],
            "hypotheses": hypotheses or [],
            "contradictions": contradictions or [],
            "open_questions": open_questions or [],
            "recommended_next_evidence": recommended_next_evidence or [],
        },
    )


@tool(args_schema=ContradictionInput)
def identify_process_contradictions(
    process_id: str,
    title: str,
    conflicting_claims: list[str],
    affected_process_area: str,
    source_names: list[str] | None = None,
    resolution_needed: str = "",
    severity: str = "medium",
) -> str:
    """
    Prepare a process contradiction record for review. Use when sources disagree
    about actors, activities, decisions, handoffs, exceptions or controls.
    """
    return enterprise_tool_result(
        status="prepared",
        action="identify_process_contradictions",
        entity_type="process_contradiction",
        entity_id=process_id,
        summary=title,
        payload={
            "process_id": process_id,
            "title": title,
            "conflicting_claims": conflicting_claims,
            "affected_process_area": affected_process_area,
            "source_names": source_names or [],
            "resolution_needed": resolution_needed,
            "severity": severity,
        },
    )


@tool(args_schema=EvidenceCoverageInput)
def prepare_evidence_coverage_matrix(
    process_id: str,
    coverage_items: list[dict],
    modeling_blockers: list[str] | None = None,
) -> str:
    """
    Prepare an evidence coverage matrix by process area. Use as the gate between
    evidence synthesis and ProcessUnderstanding modeling.
    """
    coverage_payload = _jsonable_items(coverage_items)
    weak_areas = [
        item.get("process_area")
        for item in coverage_payload
        if item.get("coverage") in {"none", "weak"}
    ]
    blockers = modeling_blockers or []
    status = "ready_for_modeling" if not blockers and len(weak_areas) <= 2 else "evidence_required"

    return enterprise_tool_result(
        status=status,
        action="prepare_evidence_coverage_matrix",
        entity_type="process_evidence_coverage",
        entity_id=process_id,
        summary=f"Evidence coverage assessed across {len(coverage_items)} process areas.",
        payload={
            "process_id": process_id,
            "coverage_items": coverage_payload,
            "weak_areas": weak_areas,
            "modeling_blockers": blockers,
        },
        warnings=blockers,
    )


EVIDENCE_TOOL_POLICY = """
Process Evidence subagent tools.

The Evidence subagent owns source custody, claim extraction, confidence,
contradictions, hypotheses and evidence coverage. It prepares and indexes
enterprise Knowledge Graph artifacts for process-scoped GraphRAG retrieval.
""".strip()


evidence_tools = [
    get_process_evidence_brief,
    manage_process_evidence,
    extract_process_claims,
    synthesize_process_evidence,
    prepare_evidence_coverage_matrix,
    extract_process_graph_from_evidence,
    index_process_evidence_graph,
]
