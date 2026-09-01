"""Modelli-argomento per gli strumenti di estrazione KG.

I toolset (``process_memory`` / ``project_memory``) usano queste classi come
schema degli argomenti che l'LLM riempie. La scrittura vera passa da
``backend.memory.knowledge_graph.mirror`` -> ``canonical.write_evidence``; la
lettura da ``backend.memory.gateway``. Non esistono piu' modelli di I/O verso
un vecchio store (rimosso nel cutover "Cervello DeliR").
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


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
