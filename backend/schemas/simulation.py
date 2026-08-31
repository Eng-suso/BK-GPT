from typing import Any, Literal

from pydantic import BaseModel, Field


SimulationRunStatus = Literal["pending", "completed", "failed"]
DistributionName = Literal["norm", "expon", "fixed"]


class SimResourceConfig(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    cost_per_hour: float = Field(ge=0)
    amount: int = Field(ge=1, le=1000)


class SimTaskConfig(BaseModel):
    element_id: str = Field(min_length=1)
    mean_seconds: float = Field(gt=0)
    distribution: DistributionName = "norm"
    resource_id: str | None = None


class SimGatewayBranchConfig(BaseModel):
    flow_id: str = Field(min_length=1)
    probability: float = Field(ge=0, le=1)


class SimGatewayConfig(BaseModel):
    element_id: str = Field(min_length=1)
    branches: list[SimGatewayBranchConfig] = Field(default_factory=list)


class CreateSimulationRunRequest(BaseModel):
    scenario_name: str = "Baseline AS-IS"
    total_cases: int = Field(default=100, ge=1, le=100_000)
    start_date: str | None = None
    current_bpmn_xml: str | None = None
    arrival_interval_seconds: int = Field(default=1800, ge=1)
    default_task_duration_seconds: int = Field(default=900, ge=1)
    default_cost_per_hour: float = Field(default=35.0, ge=0)
    resource_amount: int = Field(default=1, ge=1, le=1000)
    resource_name: str = "Operatore"
    # Optional per-element overrides (phase 2). When omitted, the global
    # defaults above drive every task / gateway / resource — unchanged behaviour.
    resources: list[SimResourceConfig] | None = None
    tasks: list[SimTaskConfig] | None = None
    gateways: list[SimGatewayConfig] | None = None
    # Optional client-supplied retry token. When absent the server derives a key
    # from the scenario inputs so a duplicate submit while a run is still
    # in flight returns the existing run instead of launching a second one.
    idempotency_key: str | None = Field(default=None, max_length=128)


class ScenarioTemplateRequest(BaseModel):
    current_bpmn_xml: str | None = None


class ScenarioTemplateTask(BaseModel):
    element_id: str
    name: str
    type: str


class ScenarioTemplateBranch(BaseModel):
    flow_id: str
    flow_name: str
    target_name: str


class ScenarioTemplateGateway(BaseModel):
    element_id: str
    name: str
    type: str
    branches: list[ScenarioTemplateBranch]


class ScenarioTemplateResponse(BaseModel):
    tasks: list[ScenarioTemplateTask] = Field(default_factory=list)
    gateways: list[ScenarioTemplateGateway] = Field(default_factory=list)


class SimulationRunResponse(BaseModel):
    id: int
    bpmn_model_id: str
    process_id: str
    scenario_name: str
    engine: str
    status: SimulationRunStatus
    idempotency_key: str | None = None
    request: dict[str, Any] = Field(default_factory=dict)
    scenario: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    outputs: list[str] = Field(default_factory=list)
    # Full-log KPI summary (cycle/waiting/cost percentiles, per-activity stats,
    # diagnostic bottleneck). None until the run completes with an event log.
    summary: dict[str, Any] | None = None
    error: str | None = None
    created_at: str
    completed_at: str | None = None


class SimulationReplayResponse(BaseModel):
    """The heavy display artifact — sampled case paths + bucketed time series +
    flow volumes. Served by its own endpoint so run list / detail stay lean."""

    run_id: int
    schema_version: int
    replay: dict[str, Any] = Field(default_factory=dict)


# --- Input confidence / scenario provenance (phase 5) ------------------------


class ScenarioProvenanceRequest(BaseModel):
    current_bpmn_xml: str | None = None


class ProvenanceRef(BaseModel):
    """Pointer back into the process-understanding artifact that grounds a value."""

    field: str
    id: str | None = None
    label: str | None = None


class ScenarioElementProvenance(BaseModel):
    element_id: str
    kind: Literal["activity", "gateway"]
    name: str
    # Which scenario parameter the consultant sets for this element.
    parameter: Literal["duration", "branching"]
    # Where the element itself came from — discovery evidence or a model inference.
    origin: Literal["interview", "ai_inferred"]
    # How well grounded the parameter is, before the consultant confirms it.
    confidence: Literal["high", "medium", "low"]
    # Short verbatim snippets from the interview / discovery notes.
    evidence: list[str] = Field(default_factory=list)
    # Gateway outcomes still flagged as inferred / assumed (0 for activities).
    open_questions: int = 0
    hint_ref: ProvenanceRef | None = None


class ScenarioProvenanceResponse(BaseModel):
    """Per-element structural provenance for the scenario builder. The frontend
    combines this with the local draft (default vs consultant-set) to roll up a
    Simulation Readiness score."""

    has_discovery: bool = False
    process_confidence: Literal["high", "medium", "low"] | None = None
    # Discovery readiness, rescaled to 0–100 from the 1–10 quality score.
    readiness_score: int | None = None
    missing_information: list[str] = Field(default_factory=list)
    weak_points: list[str] = Field(default_factory=list)
    elements: list[ScenarioElementProvenance] = Field(default_factory=list)
