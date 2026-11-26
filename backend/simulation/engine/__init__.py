"""Simulation Engine Interface (ENG-01): l'unica porta fra l'IR e il motore.

Il resto del prodotto (canvas, agenti, API, coda) parla con il motore solo da
qui, in cinque verbi:

- **valida**: ``prepare_bpmn`` porta il BPMN nella forma che il motore esegue,
  ``validate`` lo rifiuta se il motore non puo' eseguirlo, ``compatibility_report``
  spiega al consulente che cosa diventa ogni elemento;
- **compila**: ``compile`` traduce il Simulation IR nello scenario del motore;
- **esegue**: ``run`` simula e restituisce statistiche e log degli eventi;
- **annulla**: ``cancel`` interrompe un run in volo;
- **risultati**: ``read_log``, ``summarize_run`` e ``summarize_events`` leggono
  il log del motore come eventi e KPI con la stessa definizione per ogni motore.

Prosimos 2.1 e' il motore dell'MVP e vive dietro questa interfaccia come
adattatore (``backend.simulation.engine.prosimos`` e i moduli che usa). Nessun
modulo fuori dall'adattatore lo importa: lo blocca in CI la regola ast-grep
``python-engine-outside-adapter``. Un motore nuovo (ENG-02) e' un'altra classe
che rispetta ``SimulationEngine``, registrata in ``get_engine``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache
from typing import TYPE_CHECKING, Protocol

from backend.simulation.models import (
    ProsimosScenario as CompiledScenario,
    ProsimosSimulationRequest as EngineRunRequest,
    ProsimosSimulationResult as EngineRunResult,
)

if TYPE_CHECKING:
    from backend.schemas.simulation import BpmnCompatibilityResponse
    from backend.simulation.ir.model import SimulationModel

__all__ = [
    "CompiledScenario",
    "EngineCancelled",
    "EngineError",
    "EngineLogError",
    "EngineRunRequest",
    "EngineRunResult",
    "LogEvent",
    "SimulationEngine",
    "after_warmup",
    "get_engine",
]

#: Il motore dell'MVP. Il nome e' quello che ogni run salva in ``engine``.
DEFAULT_ENGINE = "prosimos"


class EngineError(RuntimeError):
    """Il motore non ha eseguito il run: il messaggio dice al consulente cosa fare."""


class EngineCancelled(EngineError):
    """Il run e' stato annullato mentre il motore lo eseguiva (``cancel``)."""


class EngineLogError(ValueError):
    """Il log degli eventi del motore non si legge nella forma attesa."""


@dataclass(slots=True)
class LogEvent:
    """Un evento del log di un run, uguale per ogni motore (tempi in secondi epoch)."""

    case_id: str
    activity: str
    enable: float
    start: float
    end: float
    resource: str
    # Gli attributi che il motore scrive accanto all'evento (del caso o
    # dell'evento): il valore del caso a quell'evento, come testo.
    attributes: dict[str, str] = field(default_factory=dict)


def after_warmup(events: list[LogEvent], warmup_cases: int) -> list[LogEvent]:
    """Gli eventi dei casi arrivati dopo i primi ``warmup_cases`` (SIM-03).

    Il sistema parte vuoto: i primi casi trovano code corte e risorse libere, e
    i loro tempi non dicono com'e' il processo a regime. Senza riscaldamento,
    gli stessi eventi.
    """
    if warmup_cases <= 0:
        return events
    arrival: dict[str, float] = {}
    for ev in events:
        arrival[ev.case_id] = min(arrival.get(ev.case_id, ev.enable), ev.enable)
    warm = set(sorted(arrival, key=lambda case_id: (arrival[case_id], case_id))[:warmup_cases])
    return [ev for ev in events if ev.case_id not in warm]


class SimulationEngine(Protocol):
    """Quello che il prodotto chiede a un motore di simulazione."""

    #: Il nome salvato su ogni run (``simulation_runs.engine``).
    name: str

    # --- valida ---------------------------------------------------------- #
    def prepare_bpmn(self, bpmn_xml: str) -> str:
        """Il BPMN riscritto nella forma che il motore esegue, con gli stessi id.

        Su un XML che non si legge restituisce l'originale: lo rifiuta ``validate``.
        """
        ...

    def validate(self, bpmn_xml: str) -> None:
        """``EngineError`` se il motore non puo' eseguire questo BPMN (gia' preparato)."""
        ...

    def compatibility_report(self, bpmn_xml: str) -> BpmnCompatibilityResponse:
        """Che cosa diventa ogni elemento del BPMN quando lo esegue questo motore."""
        ...

    # --- compila --------------------------------------------------------- #
    def compile(self, model: SimulationModel) -> dict:
        """Lo scenario del motore che esegue ``model``, senza perdere nulla."""
        ...

    # --- esegue e annulla ------------------------------------------------ #
    async def run(self, request: EngineRunRequest) -> EngineRunResult:
        """Esegue il run e restituisce statistiche e log; ``EngineError`` se non riesce."""
        ...

    def cancel(self, request: EngineRunRequest) -> bool:
        """Annulla il run in volo di questa richiesta: ``run`` alza ``EngineCancelled``.

        ``False`` se quella richiesta non sta girando su questo motore.
        """
        ...

    # --- risultati ------------------------------------------------------- #
    def read_log(self, log_csv: str) -> list[LogEvent]:
        """Il log degli eventi salvato di un run; ``EngineLogError`` se non si legge."""
        ...

    def resource_pool(self, resource: str) -> str:
        """Il gruppo di risorse (ruolo) di una risorsa scritta nel log."""
        ...

    def summarize_run(
        self,
        result: EngineRunResult,
        *,
        bpmn_xml: str,
        scenario: CompiledScenario,
        warmup_cases: int = 0,
        horizon: tuple[float, int] | None = None,
    ) -> tuple[dict, dict]:
        """KPI e replay di un run, dal suo log e dalle statistiche del motore."""
        ...

    def summarize_events(self, events: list[LogEvent], *, name_to_element_id: dict[str, str]) -> dict:
        """I KPI di un log qualsiasi (anche reale) con la definizione dei run simulati."""
        ...


def get_engine(name: str = DEFAULT_ENGINE) -> SimulationEngine:
    """Il motore registrato con quel nome; per l'MVP solo Prosimos.

    Uno per processo e per nome: ``run`` e ``cancel`` devono parlare con la
    stessa istanza, comunque la si chieda.
    """
    return _engine(name)


@cache
def _engine(name: str) -> SimulationEngine:
    if name == "prosimos":
        # Caricato solo qui: l'adattatore importa moduli che a loro volta usano
        # i tipi di questa interfaccia.
        from backend.simulation.engine.prosimos import ProsimosEngine

        return ProsimosEngine()
    raise ValueError(f"Motore di simulazione sconosciuto: {name!r}")
