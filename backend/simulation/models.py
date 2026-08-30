from typing import Any

from pydantic import BaseModel, Field


class BpmnTask(BaseModel):
    id: str
    name: str
    type: str = "task"


class BpmnFlow(BaseModel):
    id: str
    name: str = ""
    target_name: str = ""


class BpmnGateway(BaseModel):
    id: str
    name: str = ""
    type: str = "exclusiveGateway"
    outgoing_flows: tuple[BpmnFlow, ...] = Field(default_factory=tuple)

    @property
    def outgoing_flow_ids(self) -> tuple[str, ...]:
        return tuple(flow.id for flow in self.outgoing_flows)


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
