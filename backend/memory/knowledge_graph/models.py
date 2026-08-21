from typing import Literal

from pydantic import BaseModel, Field, field_validator


KGScope = Literal["project", "process", "canvas"]


class KnowledgeGraphRelationship(BaseModel):
    source: str = Field(description="Source node, e.g. process:otc, activity:validate_order, source:interview_ops.")
    relation: str = Field(description="Enterprise relation label, e.g. DEPENDS_ON, SUPPORTS, BLOCKS, OWNS.")
    target: str = Field(description="Target node.")
    evidence: str = Field(default="", description="Short source-backed evidence statement.")
    confidence: float = Field(default=0.6, ge=0.0, le=1.0, description="Confidence in the relation.")
    confirmed: bool = Field(default=False, description="Whether this relation has been validated.")
    source_ref: str | None = Field(default=None, description="Optional source_id, episode_id or document id.")

    @field_validator("source", "relation", "target")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        cleaned = " ".join(str(value or "").split())
        if not cleaned:
            raise ValueError("field cannot be empty")
        return cleaned


class KnowledgeGraphClaim(BaseModel):
    claim: str = Field(description="Atomic source-backed claim.")
    process_area: str = Field(description="Area: scope, actor, activity, decision, handoff, system, data, exception, control, timing.")
    source_name: str = Field(description="Evidence source name.")
    confidence: Literal["low", "medium", "high", "unknown"] = "medium"
    status: Literal["confirmed", "partial", "contradicted", "inferred", "unsupported"] = "partial"
    linked_element_hint: str | None = Field(default=None, description="Optional process/BPMN element name or id.")


class KnowledgeGraphGap(BaseModel):
    title: str = Field(description="Short gap title.")
    missing_information: str = Field(description="What information is missing.")
    affected_process_ids: list[str] = Field(default_factory=list, description="Affected process ids.")
    required_evidence: str = Field(default="", description="Evidence needed to close the gap.")
    severity: str = Field(default="medium", description="low, medium, high, critical or blocking.")


class KnowledgeGraphContradiction(BaseModel):
    title: str = Field(description="Short contradiction title.")
    conflicting_claims: list[str] = Field(description="Claims that cannot all be true.")
    affected_process_ids: list[str] = Field(default_factory=list, description="Affected process ids.")
    resolution_question: str = Field(description="Question or evidence needed to resolve the contradiction.")
    severity: str = Field(default="medium", description="low, medium, high, critical or blocking.")


class KnowledgeGraphImpact(BaseModel):
    title: str = Field(description="Short impact title.")
    impact_area: str = Field(description="cost, revenue, working_capital, risk, quality, time, compliance, efficiency, or ROI.")
    affected_process_ids: list[str] = Field(default_factory=list, description="Affected process ids.")
    mechanism: str = Field(description="How the issue or dependency creates business impact.")
    evidence: str = Field(default="", description="Evidence supporting this impact.")
    confidence: float = Field(default=0.6, ge=0.0, le=1.0)


class KnowledgeGraphEvidence(BaseModel):
    project_id: str = Field(description="Project scope for the enterprise KG.")
    scope: KGScope = Field(description="Primary graph scope for this evidence package.")
    source_title: str = Field(description="Human-readable source title.")
    raw_content: str = Field(default="", description="Raw or summarized source content used for extraction.")
    reason: str = Field(description="Why this graph package is being indexed.")
    process_ids: list[str] = Field(default_factory=list, description="Related process ids.")
    entities: list[str] = Field(default_factory=list, description="Named enterprise entities.")
    claims: list[KnowledgeGraphClaim] = Field(default_factory=list)
    relationships: list[KnowledgeGraphRelationship] = Field(default_factory=list)
    gaps: list[KnowledgeGraphGap] = Field(default_factory=list)
    contradictions: list[KnowledgeGraphContradiction] = Field(default_factory=list)
    impacts: list[KnowledgeGraphImpact] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list, description="source_id, episode_id or document ids.")


class KnowledgeGraphQuery(BaseModel):
    project_id: str = Field(description="Project scope for enterprise retrieval.")
    query: str = Field(description="Relation-heavy retrieval question.")
    relation_focus: str = Field(description="Relation area to inspect.")
    reason: str = Field(description="Why retrieval is needed now.")
    process_ids: list[str] = Field(default_factory=list, description="Optional process filter.")
    entities: list[str] = Field(default_factory=list, description="Entity anchors.")
    limit: int = Field(default=8, ge=1, le=20)


class KnowledgeGraphContext(BaseModel):
    status: Literal["ok", "empty", "not_configured"] = "ok"
    backend: str = Field(description="Retrieval backend name.")
    project_id: str
    query: str
    relation_focus: str
    matches: list[dict] = Field(default_factory=list)
    caveat: str = Field(default="Use workspace DB as authoritative operational state.")
