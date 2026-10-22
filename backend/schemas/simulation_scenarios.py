"""SIM-14: il workspace degli scenari AS-IS | A | B | C di un processo."""

import json
from datetime import date
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Alternative oltre l'AS-IS: A, B, C, D, E.
SCENARIO_LABELS = ("A", "B", "C", "D", "E")
BASELINE_LABEL = "AS-IS"
# La bozza del pannello pesa qualche KB; un tetto evita righe enormi.
MAX_DRAFT_BYTES = 512_000
MAX_PATCH_OPS = 500
# Il seed comune sta in una colonna intera e le ripetizioni (fino a 20) usano
# seed consecutivi: l'ultimo deve restare nell'intero.
WORKSPACE_SEED_MAX = 2**31 - 1 - 20


class ScenarioIdStep(BaseModel):
    """Un elemento di una lista, per il suo ``id`` (risorse, calendari, attributi)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=128)


ScenarioPathStep = Annotated[str, Field(min_length=1, max_length=128)] | ScenarioIdStep


class ScenarioPatchOp(BaseModel):
    """Una differenza dello scenario dall'AS-IS (``backend/simulation/scenario_patch.py``)."""

    model_config = ConfigDict(extra="forbid")

    op: Literal["set", "remove", "order"]
    path: list[ScenarioPathStep] = Field(min_length=1, max_length=12)
    value: Any = None
    ids: list[Annotated[str, Field(min_length=1, max_length=128)]] | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _shape(self) -> "ScenarioPatchOp":
        if (self.op == "order") != (self.ids is not None):
            raise ValueError("Solo un'operazione 'order' porta gli 'ids', e li porta sempre.")
        if self.op != "set" and self.value is not None:
            raise ValueError("Solo un'operazione 'set' porta un valore.")
        return self


def _json_bytes(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, default=str).encode("utf-8"))


def _check_draft_size(draft: dict[str, Any]) -> dict[str, Any]:
    if _json_bytes(draft) > MAX_DRAFT_BYTES:
        raise ValueError("La bozza dello scenario e' troppo grande.")
    return draft


def _check_patch_size(patch: list[ScenarioPatchOp] | None) -> list[ScenarioPatchOp] | None:
    # I valori di un 'set' possono essere sezioni intere: lo stesso tetto della bozza.
    if patch is not None and _json_bytes([op.model_dump(mode="json") for op in patch]) > MAX_DRAFT_BYTES:
        raise ValueError("La patch dello scenario e' troppo grande.")
    return patch


class PutScenarioBaselineRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    draft: dict[str, Any]
    # Assente: resta quello di prima (alla creazione se ne estrae uno).
    seed: int | None = Field(default=None, ge=0, le=WORKSPACE_SEED_MAX)
    # La revisione su cui il consulente ha lavorato; assente solo per creare l'AS-IS.
    revision: int | None = Field(default=None, ge=1)

    _draft_size = field_validator("draft")(_check_draft_size)


class CreateScenarioRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    patch: list[ScenarioPatchOp] = Field(default_factory=list, max_length=MAX_PATCH_OPS)

    _patch_size = field_validator("patch")(_check_patch_size)


class UpdateScenarioRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    patch: list[ScenarioPatchOp] | None = Field(default=None, max_length=MAX_PATCH_OPS)
    revision: int = Field(ge=1)

    _patch_size = field_validator("patch")(_check_patch_size)


# --- SIM-28: previsto contro osservato -----------------------------------------

OutcomeKpi = Literal["cycle", "waiting", "costPerCase", "throughput"]


class PredictedKpi(BaseModel):
    """Il KPI come il workspace lo prevedeva quando l'alternativa e' stata scelta."""

    as_is: float = Field(gt=0, allow_inf_nan=False)
    alternative: float = Field(ge=0, allow_inf_nan=False)
    # Mezza ampiezza al 95% della differenza alternativa - AS-IS, con le ripetizioni.
    half: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class PutScenarioOutcomeRequest(BaseModel):
    """L'alternativa e' stata implementata: data, previsione e i log reali prima e dopo.

    Prima e dopo possono essere lo stesso log: conta la data d'inizio di ogni caso.
    """

    model_config = ConfigDict(extra="forbid")

    implemented_on: date
    before_event_log_id: str = Field(min_length=1, max_length=64)
    after_event_log_id: str = Field(min_length=1, max_length=64)
    as_is_run_id: int | None = None
    alternative_run_id: int | None = None
    predicted: dict[OutcomeKpi, PredictedKpi] = Field(min_length=1)


class ScenarioOutcomeLog(BaseModel):
    event_log_id: str
    name: str
    cases: int


class ScenarioOutcomeKpi(BaseModel):
    """Variazioni relative: -0,2 vuol dire il 20% in meno dell'AS-IS (o del prima)."""

    kpi: OutcomeKpi
    predicted_change: float
    predicted_low: float | None = None
    predicted_high: float | None = None
    before: float | None = None
    after: float | None = None
    observed_change: float | None = None
    # Osservato meno previsto, in punti della variazione relativa.
    error: float | None = None
    # L'osservato cade nell'intervallo previsto; None senza intervallo o senza osservato.
    within: bool | None = None


class ScenarioOutcomeResponse(BaseModel):
    implemented_on: str
    recorded_at: str
    as_is_run_id: int | None = None
    alternative_run_id: int | None = None
    before: ScenarioOutcomeLog
    after: ScenarioOutcomeLog
    kpis: list[ScenarioOutcomeKpi]


class SimulationScenarioResponse(BaseModel):
    id: int
    kind: Literal["baseline", "alternative"]
    label: str
    name: str
    revision: int
    # La bozza risolta: per un'alternativa, l'AS-IS con la patch applicata.
    draft: dict[str, Any]
    # Le operazioni come salvate (gia' validate da ``ScenarioPatchOp`` in ingresso).
    patch: list[dict[str, Any]]
    # Indici delle operazioni della patch che non si applicano piu' all'AS-IS.
    conflicts: list[int]
    created_at: str
    updated_at: str
    # SIM-28: l'alternativa implementata, con quanto aveva ragione la previsione.
    outcome: ScenarioOutcomeResponse | None = None


class SimulationScenarioWorkspaceResponse(BaseModel):
    bpmn_model_id: str
    # L'impronta del BPMN salvato (SIM-14b): un run con un'altra impronta e' da rifare.
    bpmn_fingerprint: str | None = None
    seed: int | None
    baseline: SimulationScenarioResponse | None
    alternatives: list[SimulationScenarioResponse]
