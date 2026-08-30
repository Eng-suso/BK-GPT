from typing import Any

from pydantic import BaseModel, Field


class BpmnTask(BaseModel):
    id: str
    name: str


class BpmnGateway(BaseModel):
    id: str
    outgoing_flow_ids: tuple[str, ...] = Field(default_factory=tuple)


class ProsimosScenario(BaseModel):
    payload: dict[str, Any]
    task_count: int
    gateway_count: int


class ProsimosSimulationRequest(BaseModel):
    bpmn_xml: str
    scenario: ProsimosScenario
    total_cases: int
    start_date: str | None = None


class ProsimosSimulationResult(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)
    outputs: list[str] = Field(default_factory=list)
