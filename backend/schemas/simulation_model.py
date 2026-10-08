"""Contratto di run sull'IR (SIM-37): la richiesta v2 e la baseline del processo.

Sta fuori da ``schemas/simulation.py`` perche' l'IR importa quel modulo (il
ponte dalla richiesta v1): tenerli insieme farebbe un import circolare.

La v1 (``CreateSimulationRunRequest``) resta il ponte per la UI di oggi. La v2
porta il modello esplicito, o una patch sulla baseline del BPMN: tutto cio' che
l'IR sa esprimere - sei distribuzioni, calendari per risorsa, piu' risorse per
attivita', rami con regole, attributi del caso, priorita' - arriva al motore.
"""

from pydantic import BaseModel, Field, model_validator

from backend.simulation.ir.model import SimulationModel
from backend.simulation.ir.patch import ModelPatch


class CreateSimulationModelRunRequest(BaseModel):
    """Un run descritto dall'IR: ``model`` intero oppure ``patch`` sulla baseline.

    Senza nessuno dei due si simula la baseline, cioe' il BPMN con i default
    dichiarati come assunzioni.
    """

    scenario_name: str = Field(default="Baseline AS-IS", max_length=200)
    total_cases: int = Field(default=100, ge=1, le=100_000)
    start_date: str | None = None
    current_bpmn_xml: str | None = None
    model: SimulationModel | None = None
    patch: ModelPatch | None = None
    idempotency_key: str | None = Field(default=None, max_length=128)
    seed: int | None = Field(default=None, ge=0, le=2**32 - 1)

    @model_validator(mode="after")
    def _model_or_patch(self):
        if self.model is not None and self.patch is not None:
            raise ValueError("Indica il modello intero oppure una patch sulla baseline, non entrambi.")
        return self


class SimulationModelRequest(BaseModel):
    current_bpmn_xml: str | None = None


class SimulationModelResponse(BaseModel):
    """L'IR di partenza del processo: cio' che la UI mostra e una patch modifica."""

    bpmn_model_id: str
    model: SimulationModel


class SimulationRunModelResponse(BaseModel):
    """Il modello IR che un run ha simulato (SIM-20a).

    ``model`` e' ``None`` per i run creati prima che il modello si conservasse:
    per quelli resta la richiesta v1 del run.
    """

    run_id: int
    model: SimulationModel | None = None
