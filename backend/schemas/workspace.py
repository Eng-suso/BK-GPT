from typing import Any

from pydantic import BaseModel, Field


class CreateClientRequest(BaseModel):
    name: str
    sector: str = "Non specificato"
    status: str = "Prospect"
    owner: str = "Da assegnare"
    contact: str = ""


class CreateProjectRequest(BaseModel):
    client_id: str
    name: str
    phase: str = "Discovery"
    status: str = "Bozza"
    progress: int = 0
    next_step: str = "Definire perimetro e fonti iniziali"
    milestones: list[str] = Field(default_factory=list)
    open_issues: list[str] = Field(default_factory=list)
    deliverables: list[str] = Field(default_factory=list)


class CreateProcessRequest(BaseModel):
    name: str
    stage: str = "AS-IS"
    status: str = "Bozza"
    owner: str = "Da assegnare"
    readiness: int = 0


class CreateProjectSourceRequest(BaseModel):
    name: str
    type: str = "Fonte"
    meta: str = ""
    process_id: str | None = None


class CreateProjectDecisionRequest(BaseModel):
    title: str
    owner: str = "Da assegnare"
    status: str = "Aperta"
    process_id: str | None = None


class UpdateBpmnModelRequest(BaseModel):
    xml: str


class UpdateBpmnReviewRequest(BaseModel):
    bpmn_brief: str


class ClientResponse(BaseModel):
    id: str
    name: str
    sector: str
    status: str
    projects: int
    next_activity: str
    owner: str
    contact: str
    processes: list[str]
    documents: list[str]


class ProjectProcessResponse(BaseModel):
    id: str
    project_id: str
    bpmn_model_id: str
    name: str
    stage: str
    status: str
    owner: str
    readiness: int


class BpmnModelResponse(BaseModel):
    id: str
    process_id: str
    name: str
    xml: str | None = None


class BpmnVersionResponse(BaseModel):
    id: int
    bpmn_model_id: str
    process_id: str
    xml: str
    change_summary: str
    source: str
    created_at: str


class RestoreBpmnVersionResponse(BaseModel):
    bpmn_model: BpmnModelResponse
    restored_from: BpmnVersionResponse
    created_version: BpmnVersionResponse


class BpmnReviewResponse(BaseModel):
    bpmn_model_id: str
    process_id: str
    source_text: str
    process_understanding: dict[str, Any] = Field(default_factory=dict)
    bpmn_semantic_model: dict[str, Any] = Field(default_factory=dict)
    quality_report: dict[str, Any] = Field(default_factory=dict)
    bpmn_brief: str
    readiness_score: int
    missing_information: list[str]
    status: str = "pending"
    created_at: str
    updated_at: str


class ApproveBpmnReviewResponse(BaseModel):
    bpmn_model: BpmnModelResponse
    review: BpmnReviewResponse


class ProjectSourceResponse(BaseModel):
    id: str
    project_id: str
    process_id: str | None = None
    name: str
    type: str
    meta: str


class ProjectDecisionResponse(BaseModel):
    id: str
    project_id: str
    process_id: str | None = None
    title: str
    owner: str
    status: str


class ProjectResponse(BaseModel):
    id: str
    client_id: str
    client: str
    name: str
    phase: str
    status: str
    progress: int
    processes: int
    next_step: str
    milestones: list[str]
    open_issues: list[str]
    deliverables: list[str]
    process_items: list[ProjectProcessResponse] = Field(default_factory=list)
