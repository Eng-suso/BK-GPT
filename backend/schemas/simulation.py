from typing import Any, Literal

from pydantic import BaseModel, Field


SimulationRunStatus = Literal["pending", "completed", "failed"]


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
    # Optional client-supplied retry token. When absent the server derives a key
    # from the scenario inputs so a duplicate submit while a run is still
    # in flight returns the existing run instead of launching a second one.
    idempotency_key: str | None = Field(default=None, max_length=128)


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
    error: str | None = None
    created_at: str
    completed_at: str | None = None
