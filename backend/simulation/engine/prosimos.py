"""L'adattatore Prosimos 2.1 dietro la Simulation Engine Interface (ENG-01).

Qui e nei moduli che questa classe usa vive tutto cio' che sa di Prosimos: il
sottoinsieme di BPMN che esegue (``bpmn_normalizer``, ``compatibility``), lo
scenario JSON (``ir.compile``), il protocollo HTTP del runner
(``prosimos_adapter``) e il formato del suo log e delle sue statistiche
(``log_processor``). Fuori dall'adattatore nessuno li importa: si passa da
``backend.simulation.engine.get_engine()``.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from backend.simulation.bpmn_normalizer import normalize_bpmn_for_prosimos
from backend.simulation.compatibility import bpmn_compatibility_report
from backend.simulation.engine import (
    CompiledScenario,
    EngineCancelled,
    EngineError,
    EngineRunRequest,
    EngineRunResult,
)
from backend.simulation.ir.compile import compile_for_prosimos
from backend.simulation.log_processor import (
    activity_name_to_element_id,
    parse_prosimos_log,
    pool_key,
    process_prosimos_log,
    summarize_log_events,
)
from backend.simulation.prosimos_adapter import run_prosimos_simulation
from backend.simulation.validation import validate_simulation_bpmn

if TYPE_CHECKING:
    from backend.schemas.simulation import BpmnCompatibilityResponse


class ProsimosEngine:
    """Prosimos 2.1 tramite il runner DeliR (``ops/prosimos/runner``)."""

    name = "prosimos"

    # Funzioni pure dei moduli dell'adattatore: stesse funzioni, stessi risultati.
    prepare_bpmn = staticmethod(normalize_bpmn_for_prosimos)
    compile = staticmethod(compile_for_prosimos)
    read_log = staticmethod(parse_prosimos_log)
    activity_ids = staticmethod(activity_name_to_element_id)
    resource_pool = staticmethod(pool_key)
    summarize_events = staticmethod(summarize_log_events)

    def __init__(self) -> None:
        # I run in volo in questo processo, per richiesta (``id``), e quelli annullati.
        self._running: dict[int, asyncio.Task[EngineRunResult]] = {}
        self._cancelled: set[int] = set()

    def validate(self, bpmn_xml: str) -> None:
        try:
            validate_simulation_bpmn(bpmn_xml)
        except ValueError as exc:
            raise EngineError(str(exc)) from exc

    def compatibility_report(self, bpmn_xml: str) -> BpmnCompatibilityResponse:
        return bpmn_compatibility_report(bpmn_xml)

    async def run(self, request: EngineRunRequest) -> EngineRunResult:
        key = id(request)
        if key in self._running:
            raise EngineError("Questa richiesta sta gia' girando sul motore.")
        task = asyncio.ensure_future(run_prosimos_simulation(request))
        self._running[key] = task
        try:
            return await task
        except asyncio.CancelledError:
            if key in self._cancelled:
                # Il runner chiude comunque il suo run: la risposta, se arriva, si scarta.
                raise EngineCancelled("La simulazione e' stata annullata prima della fine.") from None
            raise
        finally:
            self._running.pop(key, None)
            self._cancelled.discard(key)

    def cancel(self, request: EngineRunRequest) -> bool:
        key = id(request)
        task = self._running.get(key)
        if task is None or task.done():
            return False
        self._cancelled.add(key)
        task.cancel()
        return True

    def summarize_run(
        self,
        result: EngineRunResult,
        *,
        bpmn_xml: str,
        scenario: CompiledScenario,
        warmup_cases: int = 0,
        horizon: tuple[float, int] | None = None,
    ) -> tuple[dict, dict]:
        if not result.event_log_csv:
            raise EngineError("il motore non ha restituito il log degli eventi")
        return process_prosimos_log(
            result.event_log_csv,
            normalized_bpmn_xml=bpmn_xml,
            scenario_payload=scenario.payload,
            prosimos_stats=result.payload,
            name_to_element_id=activity_name_to_element_id(bpmn_xml),
            warmup_cases=warmup_cases,
            horizon=horizon,
        )

