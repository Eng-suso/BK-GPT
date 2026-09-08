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
    """One atomic claim with everything needed to trace it back.

    `source_name` is the document; `attributed_to` is the voice inside it. Two
    different things: a workshop transcript is one source with many speakers,
    and attributing to one speaker what another said is exactly the defect this
    schema exists to prevent.

    The runtime does not trust `status` as a statement of how well supported a
    claim is - support is counted from the ledger (see
    `backend.memory.provenance`). What the extractor owns is the honest
    description of one source's contribution: who said it, in which scope, in
    which epistemic mode, and with which verbatim words.
    """

    claim: str = Field(description="Atomic source-backed claim.")
    process_area: str = Field(description="Area: scope, actor, activity, decision, handoff, system, data, exception, control, timing.")
    source_name: str = Field(description="Evidence source name (the document/interview).")
    attributed_to: str = Field(
        default="",
        description=(
            "Who states this inside the source: person, role or team. Required "
            "whenever the source has named speakers - never attribute to one "
            "speaker what another said."
        ),
    )
    topic: str = Field(
        default="",
        description=(
            "The SUBJECT this claim is about, e.g. 'autorizzazione della spesa'. "
            "It puts related claims next to each other. Sharing a subject is not "
            "agreeing on anything."
        ),
    )
    assertion: str = Field(
        default="",
        description=(
            "The PROPOSITION this claim asserts, e.g. \"sopra soglia l'ordine "
            "passa da un'autorizzazione\". Corroboration is counted on this: two "
            "sources count as agreeing only when they assert the same "
            "proposition, so give identical wording to claims that really say "
            "the same thing. Leave it empty and the claim stands alone."
        ),
    )
    qualifiers: list[str] = Field(
        default_factory=list,
        description=(
            "Attributes THIS source adds on top of the proposition, e.g. "
            "\"fornitore gia' conosciuto\", \"verifica formale prima "
            "dell'ordine\". Anything only this source says belongs here and not "
            "in the assertion: a sentence attributed to several sources may not "
            "carry it."
        ),
    )
    quote: str = Field(
        default="",
        description=(
            "Verbatim span copied from the source that supports this claim. Do "
            "not paraphrase and do not strengthen it - the runtime checks that "
            "this text occurs in the source."
        ),
    )
    scope_label: str = Field(
        default="",
        description=(
            "Department, role or context the claim actually covers, e.g. "
            "'Manutenzione'. Leave empty only when the source speaks about the "
            "whole process."
        ),
    )
    scope_level: Literal["stated_scope", "whole_process"] = Field(
        default="stated_scope",
        description=(
            "stated_scope: valid for scope_label only. whole_process: the source "
            "explicitly speaks for the entire process."
        ),
    )
    epistemic_status: Literal[
        "reported", "observed", "documented", "inferred", "declared_unknown"
    ] = Field(
        default="reported",
        description=(
            "reported: the source says so. observed: the source did/saw it "
            "first hand. documented: it is in an attached document. inferred: "
            "your deduction, no source states it. declared_unknown: the source "
            "explicitly says it does not know - that is information, not a gap."
        ),
    )
    confidence: Literal["low", "medium", "high", "unknown"] = "medium"
    status: Literal["confirmed", "partial", "contradicted", "inferred", "unsupported"] = "partial"
    linked_element_hint: str | None = Field(default=None, description="Optional process/BPMN element name or id.")


class KnowledgeGraphGap(BaseModel):
    title: str = Field(description="Short gap title.")
    missing_information: str = Field(description="What information is missing.")
    affected_process_ids: list[str] = Field(default_factory=list, description="Affected process ids.")
    required_evidence: str = Field(default="", description="Evidence needed to close the gap.")
    severity: str = Field(default="medium", description="low, medium, high, critical or blocking.")


class KnowledgeGraphStance(BaseModel):
    """One side of a divergence: who says what, in which mode and scope."""

    source_name: str = Field(default="", description="Source that holds this position.")
    attributed_to: str = Field(default="", description="Person or role stating it.")
    statement: str = Field(default="", description="What this side actually says.")
    epistemic_status: Literal[
        "reported", "observed", "documented", "inferred", "declared_unknown"
    ] = Field(
        default="reported",
        description="Use declared_unknown when this side says it does not know.",
    )
    scope_label: str = Field(default="", description="Department/role this side speaks for.")
    qualifiers: list[str] = Field(
        default_factory=list,
        description="Attributes only this side adds.",
    )


class KnowledgeGraphContradiction(BaseModel):
    """A disagreement between sources, typed by what kind of disagreement it is.

    Not every difference is a contradiction. The runtime reclassifies
    (`backend.memory.provenance.classify_divergence`) and can only weaken the
    declared type: a side that says it does not know, or two sides speaking for
    different departments, never add up to an incompatibility.
    """

    title: str = Field(description="Short contradiction title.")
    conflicting_claims: list[str] = Field(description="Claims that cannot all be true.")
    divergence_type: Literal[
        "incompatible",
        "scope_difference",
        "formalization_difference",
        "knowledge_gap",
        "complementary",
        "tension_to_explore",
    ] = Field(
        default="tension_to_explore",
        description=(
            "incompatible only when both sides positively assert things that "
            "cannot both be true. Use knowledge_gap when one side declares it "
            "does not know, scope_difference when they speak for different "
            "departments, formalization_difference when it is the same practice "
            "at a different degree of formality."
        ),
    )
    stances: list[KnowledgeGraphStance] = Field(
        default_factory=list,
        description="The positions in play. Needed to type the divergence honestly.",
    )
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
