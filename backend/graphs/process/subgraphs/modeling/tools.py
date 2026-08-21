from langchain_core.tools import tool
from pydantic import BaseModel, Field

from backend import workspace_database
from backend.bpmn_semantic import build_bpmn_semantic_model, validate_bpmn_semantic_model
from backend.graphs.process.tools import (
    bpmn_semantic_model_from_payload,
    prepare_canvas_handoff,
    process_understanding_from_payload,
    process_workspace_payload,
)
from backend.process_understanding import render_process_review
from backend.toolsets.workspace import enterprise_tool_result


class ProcessUnderstandingReviewInput(BaseModel):
    process_id: str = Field(description="Current process id.")
    process_description: str = Field(
        description=(
            "Evidence-backed process description. Include confirmed flow, actors, decisions, "
            "handoffs, exceptions, data, assumptions and explicit gaps."
        )
    )
    evidence_summary: str = Field(default="", description="Sources and claims that support the description.")
    known_assumptions: list[str] = Field(default_factory=list, description="Assumptions to preserve in the review.")
    unresolved_gaps: list[str] = Field(default_factory=list, description="Open gaps to preserve as unknowns.")


class UnderstandingReadinessInput(BaseModel):
    process_id: str = Field(description="Current process id.")
    objective: str = Field(description="Why readiness is being checked.")
    minimum_readiness_score: int = Field(default=7, ge=1, le=10, description="Minimum score before canvas handoff.")


@tool(args_schema=UnderstandingReadinessInput)
def validate_process_understanding_readiness(
    process_id: str,
    objective: str,
    minimum_readiness_score: int = 7,
) -> str:
    """
    Validate whether the current ProcessUnderstanding is ready for BPMN semantic
    modeling or canvas handoff. Use before deriving BPMN or delegating to Canvas.
    """
    payload = process_workspace_payload(process_id)
    review = payload["review"]
    understanding = process_understanding_from_payload(payload)
    warnings = []

    if review is None or understanding is None:
        warnings.append("No valid ProcessUnderstanding review exists.")
        score = 0
    else:
        score = int(review.get("readiness_score") or 0)
        blocking_unknowns = [
            item.question
            for item in understanding.unknowns
            if item.severity == "blocking"
        ]
        warnings.extend(blocking_unknowns)
        if score < minimum_readiness_score:
            warnings.append("Readiness score is below the requested threshold.")

    status = "ready_for_modeling" if not warnings else "review_required"
    return enterprise_tool_result(
        status=status,
        action="validate_process_understanding_readiness",
        entity_type="process_understanding_readiness",
        entity_id=process_id,
        summary=objective,
        payload={
            "process_id": process_id,
            "minimum_readiness_score": minimum_readiness_score,
            "readiness_score": score,
            "missing_information": review.get("missing_information") if review else [],
        },
        warnings=warnings,
    )


@tool(args_schema=ProcessUnderstandingReviewInput)
def prepare_process_understanding_review(
    process_id: str,
    process_description: str,
    evidence_summary: str = "",
    known_assumptions: list[str] | None = None,
    unresolved_gaps: list[str] | None = None,
) -> str:
    """
    Build and save a pending ProcessUnderstanding/BPMNSemanticModel review for
    one process. Use only after discovery/evidence synthesis, not from generic
    free text. This does not approve or save final BPMN XML.
    """
    process = workspace_database.get_process(process_id)
    if process is None:
        raise ValueError(f"Processo non trovato: {process_id}")

    sections = [process_description.strip()]
    if evidence_summary.strip():
        sections.append("Evidence summary:\n" + evidence_summary.strip())
    if known_assumptions:
        sections.append("Known assumptions:\n" + "\n".join(f"- {item}" for item in known_assumptions))
    if unresolved_gaps:
        sections.append("Unresolved gaps:\n" + "\n".join(f"- {item}" for item in unresolved_gaps))

    review = workspace_database.prepare_bpmn_review(
        bpmn_model_id=process["bpmn_model_id"],
        process_description="\n\n".join(sections),
    )
    return enterprise_tool_result(
        status="prepared",
        action="prepare_process_understanding_review",
        entity_type="process_understanding_review",
        entity_id=process_id,
        summary=f"ProcessUnderstanding review prepared for {process['name']}.",
        payload={
            "process_id": process_id,
            "bpmn_model_id": process["bpmn_model_id"],
            "readiness_score": review["readiness_score"],
            "missing_information": review["missing_information"],
            "process_review_markdown": review["bpmn_brief"],
            "process_understanding": review["process_understanding"],
            "bpmn_semantic_model": review["bpmn_semantic_model"],
        },
        warnings=review["missing_information"],
    )


@tool
def derive_bpmn_semantic_model(process_id: str) -> str:
    """
    Derive a BPMNSemanticModel from the current ProcessUnderstanding and return
    validation warnings. Use after a ProcessUnderstanding review exists.
    """
    payload = process_workspace_payload(process_id)
    process = payload["process"]
    understanding = process_understanding_from_payload(payload)
    if understanding is None:
        raise ValueError("ProcessUnderstanding non disponibile per questo processo.")

    model = build_bpmn_semantic_model(
        process_id=f"Process_{process['id'].replace('-', '_')}",
        process_name=process["name"],
        process=understanding,
    )
    warnings = validate_bpmn_semantic_model(model)
    return enterprise_tool_result(
        status="prepared" if not warnings else "review_required",
        action="derive_bpmn_semantic_model",
        entity_type="bpmn_semantic_model",
        entity_id=process_id,
        summary=f"BPMNSemanticModel derived for {process['name']}.",
        payload={
            "process_id": process_id,
            "bpmn_model_id": process["bpmn_model_id"],
            "bpmn_semantic_model": model.model_dump(mode="json"),
            "validation_warnings": warnings,
        },
        warnings=warnings,
    )


@tool
def validate_prepared_bpmn_semantic_model(process_id: str) -> str:
    """
    Validate the BPMNSemanticModel stored in the current pending process review.
    Use before Canvas Macro handoff.
    """
    payload = process_workspace_payload(process_id)
    process = payload["process"]
    model = bpmn_semantic_model_from_payload(payload)
    if model is None:
        raise ValueError("BPMNSemanticModel non disponibile per questo processo.")

    warnings = validate_bpmn_semantic_model(model)
    return enterprise_tool_result(
        status="valid" if not warnings else "review_required",
        action="validate_prepared_bpmn_semantic_model",
        entity_type="bpmn_semantic_model_validation",
        entity_id=process_id,
        summary=f"BPMNSemanticModel validation for {process['name']}.",
        payload={
            "process_id": process_id,
            "bpmn_model_id": process["bpmn_model_id"],
            "node_count": len(model.flowNodes),
            "flow_count": len(model.sequenceFlows),
            "lane_count": len(model.lanes),
            "model_warnings": model.model_warnings,
            "validation_warnings": warnings,
        },
        warnings=warnings,
    )


@tool
def render_process_understanding_review(process_id: str) -> str:
    """
    Render the current ProcessUnderstanding as a concise human review. Use before
    asking the user to approve, correct or continue to canvas.
    """
    payload = process_workspace_payload(process_id)
    understanding = process_understanding_from_payload(payload)
    if understanding is None:
        raise ValueError("ProcessUnderstanding non disponibile per questo processo.")

    return enterprise_tool_result(
        status="ok",
        action="render_process_understanding_review",
        entity_type="process_understanding_review",
        entity_id=process_id,
        summary=f"Review for {understanding.title}.",
        payload={
            "process_id": process_id,
            "review_markdown": render_process_review(understanding),
            "process_understanding": understanding.model_dump(mode="json"),
        },
    )


MODELING_TOOL_POLICY = """
Process Modeling subagent tools.

The Modeling subagent owns the transition from evidence-backed process knowledge
to ProcessUnderstanding and BPMNSemanticModel. It must check readiness before
canvas handoff. It does not approve or save final BPMN XML.
""".strip()


modeling_tools = [
    validate_process_understanding_readiness,
    prepare_process_understanding_review,
    render_process_understanding_review,
    derive_bpmn_semantic_model,
    validate_prepared_bpmn_semantic_model,
    prepare_canvas_handoff,
]
