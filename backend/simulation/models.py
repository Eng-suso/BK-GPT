from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.simulation.ir.model import TimerEscalation


class BpmnTask(BaseModel):
    id: str
    name: str
    type: str = "task"


class BpmnWait(BaseModel):
    """SIM-11c/d: un evento intermedio rimasto nel BPMN normalizzato, che il caso aspetta.

    Un timer porta la sua durata (``seconds``); un messaggio, un segnale o una
    condizione no: la imposta il consulente.
    """

    id: str
    name: str = ""
    kind: Literal["timer", "message", "signal", "conditional"] = "timer"
    seconds: float | None = None


class BpmnFlow(BaseModel):
    id: str
    name: str = ""
    target_name: str = ""


class BpmnGateway(BaseModel):
    id: str
    name: str = ""
    type: str = "exclusiveGateway"
    outgoing_flows: tuple[BpmnFlow, ...] = Field(default_factory=tuple)
    # SIM-35: la decisione era un timer interrompente sul bordo di un'attivita'.
    escalation: TimerEscalation | None = None

    @property
    def outgoing_flow_ids(self) -> tuple[str, ...]:
        return tuple(flow.id for flow in self.outgoing_flows)


class ProsimosScenario(BaseModel):
    payload: dict[str, Any]
    task_count: int
    gateway_count: int
    # Il Simulation IR da cui viene ``payload``, serializzato (``model_dump``).
    # Il run lo conserva: e' cio' che ha simulato davvero, provenienza compresa.
    # Un dizionario e non ``SimulationModel`` per non importare l'IR da qui
    # (``ir.from_request`` importa questo modulo).
    model: dict[str, Any] | None = None
    # Il BPMN che il motore deve eseguire, se lo scenario lo ha riscritto
    # (durate condizionali, SIM-32). Assente = quello della richiesta.
    bpmn_xml: str | None = None


class ProsimosSimulationRequest(BaseModel):
    bpmn_xml: str
    scenario: ProsimosScenario
    total_cases: int
    start_date: str | None = None
    seed: int | None = None


class ProsimosSimulationResult(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)
    outputs: list[str] = Field(default_factory=list)
    # Full simulation event log (CSV text) fetched from the Prosimos service after
    # the run. None when the run failed or the log couldn't be retrieved — the
    # DeliR run still completes, only the replay artifact is missing.
    event_log_csv: str | None = None
