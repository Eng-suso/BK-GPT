from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


CanvasRoute = Literal["direct", "patch_edit", "construction", "validation", "clarification"]
CanvasMode = Literal["inspection", "patch_edit", "construction", "validation", "clarification"]


class CanvasRouteDecision(BaseModel):
    route: CanvasRoute = Field(description="Canvas owner selected for the latest request.")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    needs_clarification: bool = False
    clarification_question: str | None = None
    entity_hints: dict = Field(default_factory=dict)
    canvas_mode: CanvasMode = "inspection"
    canvas_objective: str = ""
    expected_result: str = ""
    reason: str = ""


class CanvasDelegationPayload(BaseModel):
    target: str | None = None
    route: CanvasRoute
    user_request: str
    entity_hints: dict = Field(default_factory=dict)
    expected_result: str = ""
    reason: str = ""


class CanvasPatchPlan(BaseModel):
    objective: str
    operation: str
    target_element_id: str | None = None
    target_element_label: str | None = None
    expected_locality: Literal["single_element", "few_elements", "connection_only"] = "single_element"
    requires_full_regeneration: bool = False
    validation_required: bool = True
    notes: list[str] = Field(default_factory=list)


class CanvasConstructionPlan(BaseModel):
    objective: str
    source: Literal["process_understanding", "bpmn_semantic_model", "approved_review", "explicit_xml"]
    reconstruction_scope: Literal["partial_section", "full_model"] = "partial_section"
    semantic_requirements: list[str] = Field(default_factory=list)
    unresolved_gaps: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    requires_preview: bool = True
    requires_user_approval: bool = True


class CanvasValidationReport(BaseModel):
    objective: str
    xml_valid: bool
    semantic_valid: bool | None = None
    issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
