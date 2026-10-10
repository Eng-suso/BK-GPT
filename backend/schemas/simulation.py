from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.simulation.ir.patch import ModelPatch


SimulationRunStatus = Literal["pending", "completed", "failed"]
# I nomi di Prosimos 2.1. Triangolare, Weibull e Beta non ci sono: il motore
# non le esegue (docs/simulation-prosimos-2x-spike.md).
DistributionName = Literal["fixed", "expon", "uniform", "norm", "lognorm", "gamma"]
Weekday = Literal["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]


class SimCalendarPeriodConfig(BaseModel):
    """Da un giorno a un altro (inclusi), fra due orari ``HH:MM`` o ``HH:MM:SS``."""

    from_day: Weekday
    to_day: Weekday
    begin: str = Field(min_length=5, max_length=12)
    end: str = Field(min_length=5, max_length=12)


class SimCalendarConfig(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    periods: list[SimCalendarPeriodConfig] = Field(min_length=1, max_length=50)


class SimResourceConfig(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    cost_per_hour: float = Field(ge=0)
    amount: int = Field(ge=1, le=1000)
    # Il calendario di lavoro della risorsa; assente = il calendario standard.
    calendar_id: str | None = Field(default=None, max_length=64)


class SimTaskAssignmentConfig(BaseModel):
    """Un'altra risorsa che puo' svolgere l'attivita', con la sua durata.

    I parametri della durata seguono le stesse regole di ``SimTaskConfig``.
    """

    resource_id: str = Field(min_length=1, max_length=64)
    mean_seconds: float = Field(gt=0)
    distribution: DistributionName = "norm"
    std_seconds: float | None = Field(default=None, gt=0)
    min_seconds: float | None = Field(default=None, ge=0)
    max_seconds: float | None = Field(default=None, gt=0)


class SimArrivalConfig(BaseModel):
    """Come arrivano i casi: la distribuzione del tempo fra un arrivo e il
    successivo e il calendario in cui arrivano.

    I parametri seguono le regole della durata di ``SimTaskConfig``; per
    l'esponenziale, assenti, i limiti sono 0 e 10 volte la media. Senza
    ``calendar_id`` i casi arrivano nel calendario standard.
    """

    mean_seconds: float = Field(gt=0)
    distribution: DistributionName = "expon"
    std_seconds: float | None = Field(default=None, gt=0)
    min_seconds: float | None = Field(default=None, ge=0)
    max_seconds: float | None = Field(default=None, gt=0)
    calendar_id: str | None = Field(default=None, max_length=64)


class SimSlaConfig(BaseModel):
    """L'obiettivo di servizio dello scenario (SIM-13): il caso si chiude entro
    ``target_seconds`` per almeno la quota ``share`` dei casi (0-1)."""

    target_seconds: float = Field(gt=0)
    share: float = Field(gt=0, le=1)


class SimClaimRef(BaseModel):
    """Un'affermazione di un file del cliente che il consulente ha collegato all'attivita'."""

    claim_id: int = Field(ge=1)
    label: str = Field(default="", max_length=200)


class SimTaskConfig(BaseModel):
    """La durata di un'attivita'. Oltre alla media, i parametri facoltativi:

    - ``std_seconds`` (normale, lognormale, gamma): assente = 10% della media;
    - ``min_seconds``/``max_seconds``: i limiti della distribuzione. Assenti,
      +-3 deviazioni standard (mai sotto zero), o 0 e 10 volte la media per
      l'esponenziale. L'uniforme li richiede entrambi.

    ``other_assignments``: le altre risorse che possono svolgerla, ognuna con
    la sua durata. Il motore da' il caso alla prima risorsa libera fra
    ``resource_id`` e queste.
    """

    element_id: str = Field(min_length=1)
    mean_seconds: float = Field(gt=0)
    distribution: DistributionName = "norm"
    resource_id: str | None = None
    std_seconds: float | None = Field(default=None, gt=0)
    min_seconds: float | None = Field(default=None, ge=0)
    max_seconds: float | None = Field(default=None, gt=0)
    other_assignments: list[SimTaskAssignmentConfig] = Field(default_factory=list, max_length=20)
    # Le affermazioni confermate dal consulente (SIM-07): diventano la fonte
    # ``declared`` della durata. Il valore resta quello del pannello.
    claims: list[SimClaimRef] = Field(default_factory=list, max_length=10)


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
    # Gli arrivi con distribuzione e calendario (A2-3). Se c'e', prevale su
    # ``arrival_interval_seconds``.
    arrival: SimArrivalConfig | None = None
    # L'obiettivo di servizio: il motore non lo usa, il run ne misura l'esito.
    sla: SimSlaConfig | None = None
    default_task_duration_seconds: int = Field(default=900, ge=1)
    default_cost_per_hour: float = Field(default=35.0, ge=0)
    resource_amount: int = Field(default=1, ge=1, le=1000)
    resource_name: str = "Operatore"
    # Optional per-element overrides (phase 2). When omitted, the global
    # defaults above drive every task / gateway / resource — unchanged behaviour.
    resources: list[SimResourceConfig] | None = None
    # Calendari di lavoro citati dalle risorse, oltre a quello standard.
    calendars: list[SimCalendarConfig] | None = Field(default=None, max_length=50)
    tasks: list[SimTaskConfig] | None = None
    gateways: list[SimGatewayConfig] | None = None
    # Cio' che i campi qui sopra non sanno dire (attributi del caso, rami per
    # regola, priorita'): una ``ModelPatch`` dell'IR applicata dopo la
    # traduzione della richiesta e verificata di nuovo sul BPMN.
    model_patch: ModelPatch | None = None
    # Optional client-supplied retry token. When absent the server derives a key
    # from the scenario inputs so a duplicate submit while a run is still
    # in flight returns the existing run instead of launching a second one.
    idempotency_key: str | None = Field(default=None, max_length=128)
    # Seed del motore. Con lo stesso seed e lo stesso scenario il runner rifa'
    # lo stesso log; senza, ne sceglie uno e lo restituisce nel risultato.
    seed: int | None = Field(default=None, ge=0, le=2**32 - 1)


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


class ScenarioTemplateResource(BaseModel):
    id: str
    name: str
    kind: Literal["pool", "lane"]
    bpmn_id: str
    pool_name: str | None = None
    parent_name: str | None = None
    task_ids: list[str] = Field(default_factory=list)


class ScenarioTemplateResponse(BaseModel):
    resources: list[ScenarioTemplateResource] = Field(default_factory=list)
    tasks: list[ScenarioTemplateTask] = Field(default_factory=list)
    gateways: list[ScenarioTemplateGateway] = Field(default_factory=list)
    # Il calendario che usano gli arrivi e le risorse senza calendario proprio.
    standard_calendar: SimCalendarConfig | None = None


# --- Affermazioni dei file come fonti dei parametri (SIM-07, C3) -------------


class SimulationClaimsRequest(BaseModel):
    current_bpmn_xml: str | None = None


class DurationHintResponse(BaseModel):
    text: str
    seconds: float


class ClaimProposalResponse(BaseModel):
    claim_id: int
    statement: str
    quote: str
    quote_verified: bool
    source_id: str
    source_name: str
    # Quanto del nome dell'attivita' l'affermazione nomina (0-1).
    score: float
    # Una durata citata nella fonte: un riferimento, mai il valore del parametro.
    duration_hint: DurationHintResponse | None = None


class ActivityClaimsResponse(BaseModel):
    element_id: str
    name: str
    proposals: list[ClaimProposalResponse] = Field(default_factory=list)


class SimulationClaimsResponse(BaseModel):
    """Per ogni attivita' del BPMN, le affermazioni dei file che la nominano."""

    sources: int = 0
    activities: list[ActivityClaimsResponse] = Field(default_factory=list)


# --- Compatibilita' del BPMN con il motore (SIM-05) ---------------------------

CompatibilityStatus = Literal["preserved", "approximated", "flattened", "removed"]
KpiImpact = Literal["none", "low", "medium", "high"]


class BpmnCompatibilityRequest(BaseModel):
    current_bpmn_xml: str | None = None


class BpmnElementCompatibility(BaseModel):
    """Che cosa il normalizer ha fatto di un elemento del BPMN del consulente."""

    element_id: str
    name: str = ""
    bpmn_type: str
    status: CompatibilityStatus
    impact: KpiImpact
    # Come il motore vede l'elemento: il tipo dopo la normalizzazione, oppure
    # l'elemento che lo assorbe (sottoprocesso, evento di inizio superstite).
    simulated_as: str | None = None
    # Il sottoprocesso che contiene l'elemento, quando e' stato appiattito.
    parent_id: str | None = None
    note: str = ""


class BpmnCompatibilityResponse(BaseModel):
    """Ogni elemento del BPMN, con lo stato dopo la normalizzazione.

    ``undeclared`` conta gli elementi che il normalizer ha cambiato senza una
    voce nel report: deve essere sempre zero, e un test lo controlla.
    """

    elements: list[BpmnElementCompatibility] = Field(default_factory=list)
    counts: dict[CompatibilityStatus, int] = Field(default_factory=dict)
    # Elementi non preservati che spostano i KPI (impatto diverso da "none").
    kpi_affecting: int = 0
    undeclared: int = 0


class SimulationQueueView(BaseModel):
    """Dove sta un run ``pending`` (P0.3): in coda, con la posizione, o in corso."""

    state: Literal["queued", "running"]
    position: int | None = None


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
    # Per un run ``pending`` (P0.3): ``{"state": "queued", "position": n}`` mentre
    # aspetta il suo turno, ``{"state": "running", "position": None}`` mentre gira.
    queue: SimulationQueueView | None = None


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


class ParameterSourceRef(BaseModel):
    """Mirror of the IR ``SourceRef`` (``backend/simulation/ir/model.py``).

    Kept as a plain schema: importing the IR from here would close an import
    cycle (``ir.from_request`` reads this module). A test pins the literals.
    """

    kind: Literal["claim", "source", "event_log", "document", "interview", "user"]
    id: str
    label: str | None = None


class ParameterProvenance(BaseModel):
    """Mirror of the IR ``Provenance``: the five-level origin (SIM-07)."""

    origin: Literal["observed", "inferred", "declared", "estimated", "manual"]
    confidence: Literal["high", "medium", "low"] | None = None
    sources: list[ParameterSourceRef] = Field(default_factory=list)
    note: str | None = None


class ScenarioElementProvenance(BaseModel):
    element_id: str
    kind: Literal["activity", "gateway"]
    name: str
    # Which scenario parameter the consultant sets for this element.
    parameter: Literal["duration", "branching"]
    # Where the element came from, on the IR scale (SIM-38): ``declared`` when
    # discovery grounds it, ``estimated`` when the model invented it.
    provenance: ParameterProvenance
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
