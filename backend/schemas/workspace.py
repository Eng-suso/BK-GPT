from typing import Any

from pydantic import BaseModel, Field


class CreateClientRequest(BaseModel):
    # Ogni campo oltre al nome e' opzionale davvero: `None` significa "non
    # dichiarato" e il placeholder lo mette `workspace_database.create_client`,
    # in un punto solo. Vedi `backend/workspace_defaults.py`.
    name: str
    sector: str | None = None
    status: str | None = None
    owner: str | None = None
    contact: str | None = None


class UpdateClientRequest(BaseModel):
    # Patch parziale: `None` significa "non toccare questo campo". Il consulente
    # modifica un campo alla volta dalla UI e non deve rimandare tutto il record.
    name: str | None = None
    sector: str | None = None
    status: str | None = None
    owner: str | None = None
    contact: str | None = None


class CreateProjectRequest(BaseModel):
    # Come per il cliente: `None` e' "non dichiarato", e il placeholder lo mette
    # `workspace_database.create_project`. Vedi `backend/workspace_defaults.py`.
    client_id: str
    name: str
    objective: str | None = None
    phase: str | None = None
    status: str | None = None
    progress: int = 0
    next_step: str | None = None
    milestones: list[str] = Field(default_factory=list)
    open_issues: list[str] = Field(default_factory=list)
    deliverables: list[str] = Field(default_factory=list)


class UpdateProjectRequest(BaseModel):
    # Patch parziale. Le liste arrivano intere quando arrivano: `[]` svuota,
    # `None` lascia com'e'.
    name: str | None = None
    client_id: str | None = None
    objective: str | None = None
    phase: str | None = None
    status: str | None = None
    progress: int | None = None
    next_step: str | None = None
    milestones: list[str] | None = None
    open_issues: list[str] | None = None
    deliverables: list[str] | None = None


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
    version: int = 1
    source_text: str
    process_understanding: dict[str, Any] = Field(default_factory=dict)
    bpmn_semantic_model: dict[str, Any] = Field(default_factory=dict)
    quality_report: dict[str, Any] = Field(default_factory=dict)
    bpmn_brief: str
    readiness_score: int
    missing_information: list[str]
    open_questions: list[ReviewOpenQuestionResponse] = Field(default_factory=list)
    answers: list[ReviewAnswerResponse] = Field(default_factory=list)
    status: str = "pending"
    created_at: str
    updated_at: str


class ReviewOptionResponse(BaseModel):
    """One alternative the agent proposed for an open question."""

    label: str
    implication: str = ""


class ReviewOpenQuestionResponse(BaseModel):
    """A gap in the plan the consultant can actually close."""

    question_id: str
    question: str
    affects: str = ""
    severity: str = "non_blocking"
    options: list[ReviewOptionResponse] = Field(default_factory=list)
    answer: str | None = None
    answered_at: str | None = None


class ReviewAnswerResponse(BaseModel):
    question_id: str
    question: str
    answer: str
    answered_at: str


class AnswerBpmnReviewQuestionRequest(BaseModel):
    """The consultant's answer: a proposed option, or their own words."""

    question: str
    answer: str


class BpmnReviewVersionResponse(BaseModel):
    """One recorded state of a review, with why it was written."""

    bpmn_model_id: str
    process_id: str
    version: int
    status: str
    change_summary: str
    source: str
    source_text: str
    process_understanding: dict[str, Any] = Field(default_factory=dict)
    bpmn_semantic_model: dict[str, Any] = Field(default_factory=dict)
    quality_report: dict[str, Any] = Field(default_factory=dict)
    bpmn_brief: str
    readiness_score: int
    missing_information: list[str]
    open_questions: list[ReviewOpenQuestionResponse] = Field(default_factory=list)
    answers: list[ReviewAnswerResponse] = Field(default_factory=list)
    created_at: str


class ReviseBpmnReviewRequest(BaseModel):
    """A corrected ProcessUnderstanding: the plan is rebuilt from it."""

    process_understanding: dict[str, Any]
    change_summary: str = ""


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
    objective: str = ""
    phase: str
    status: str
    progress: int
    processes: int
    next_step: str
    milestones: list[str]
    open_issues: list[str]
    deliverables: list[str]
    process_items: list[ProjectProcessResponse] = Field(default_factory=list)
