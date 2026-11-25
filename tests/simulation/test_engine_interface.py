"""ENG-01: la Simulation Engine Interface e l'adattatore Prosimos dietro di essa."""

import asyncio
import inspect
import subprocess
import sys
from pathlib import Path

import pytest

from backend.simulation.engine import (
    EngineCancelled,
    EngineError,
    EngineLogError,
    EngineRunRequest,
    EngineRunResult,
    LogEvent,
    SimulationEngine,
    after_warmup,
    get_engine,
)
from backend.simulation.engine.prosimos import ProsimosEngine
from backend.simulation.models import ProsimosScenario
from tests.simulation.engine_log import ENGINE_LOG

BPMN = (
    '<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"><process id="p">'
    '<startEvent id="s"/><task id="t" name="Controllo"/><endEvent id="e"/>'
    '<sequenceFlow id="f1" sourceRef="s" targetRef="t"/><sequenceFlow id="f2" sourceRef="t" targetRef="e"/>'
    "</process></definitions>"
)

VERBS = (
    "prepare_bpmn", "validate", "compatibility_report", "compile", "run", "cancel",
    "read_log", "activity_ids", "resource_pool", "summarize_run", "summarize_events",
)


def _request() -> EngineRunRequest:
    scenario = ProsimosScenario(payload={}, task_count=1, gateway_count=0)
    return EngineRunRequest(bpmn_xml="<bpmn/>", scenario=scenario, total_cases=3)


def test_the_registry_gives_prosimos_once_and_refuses_unknown_engines():
    engine = get_engine()
    assert isinstance(engine, ProsimosEngine)
    assert engine is get_engine("prosimos")
    assert engine.name == "prosimos"
    with pytest.raises(ValueError, match="sconosciuto"):
        get_engine("motore-che-non-esiste")


def test_the_prosimos_adapter_implements_every_verb_of_the_interface():
    engine = get_engine()
    for verb in VERBS:
        assert hasattr(SimulationEngine, verb), verb
        assert callable(getattr(engine, verb)), verb
    assert inspect.iscoroutinefunction(engine.run)


def test_historical_names_resolve_to_the_same_adapter_functions():
    # I nomi storici (usati da test e script) restano gli stessi oggetti: stesso JSON, stessi KPI.
    from backend.simulation.bpmn_normalizer import normalize_bpmn_for_prosimos
    from backend.simulation.ir import compile_for_prosimos
    from backend.simulation.ir.compile import compile_for_prosimos as compile_function
    from backend.simulation.log_processor import LogEvent as LegacyLogEvent
    from backend.simulation.log_processor import ProsimosLogError, after_warmup as legacy_warmup, parse_prosimos_log
    from backend.simulation.prosimos_adapter import ProsimosError

    engine = get_engine()
    assert compile_for_prosimos is compile_function is engine.compile
    assert engine.prepare_bpmn(BPMN) == normalize_bpmn_for_prosimos(BPMN)
    assert engine.read_log(ENGINE_LOG) == parse_prosimos_log(ENGINE_LOG)
    assert LegacyLogEvent is LogEvent and legacy_warmup is after_warmup
    assert issubclass(ProsimosError, EngineError)
    assert issubclass(ProsimosLogError, EngineLogError)


def test_compiling_through_the_registry_loads_only_the_ir():
    # Il test del contratto compila nel venv del runner, senza httpx ne' le impostazioni del backend.
    code = (
        "import sys; from backend.simulation.ir import compile_for_prosimos; "
        "loaded = [m for m in ('backend.simulation.prosimos_adapter', 'backend.simulation.log_processor', "
        "'backend.settings', 'httpx') if m in sys.modules]; print(loaded)"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True,
                         cwd=Path(__file__).resolve().parents[2])
    assert out.stdout.strip() == "[]"


def test_read_log_gives_engine_neutral_events():
    events = get_engine().read_log(ENGINE_LOG)
    assert events and all(isinstance(event, LogEvent) for event in events)
    with pytest.raises(EngineLogError):
        get_engine().read_log("")


def test_validate_speaks_engine_errors():
    with pytest.raises(EngineError, match="XML BPMN non valido"):
        get_engine().validate("<non è xml")


def _slow_adapter(monkeypatch, started: asyncio.Event):
    async def slow(request):
        started.set()
        await asyncio.sleep(3600)
        return EngineRunResult()

    monkeypatch.setattr("backend.simulation.prosimos_adapter.run_prosimos_simulation", slow)


def test_cancel_stops_the_run_in_flight_and_frees_the_request(monkeypatch):
    engine = ProsimosEngine()
    request = _request()

    async def scenario():
        started = asyncio.Event()
        _slow_adapter(monkeypatch, started)
        running = asyncio.create_task(engine.run(request))
        await started.wait()
        assert engine.cancel(request) is True
        with pytest.raises(EngineCancelled):
            await running
        # Finito il run, la stessa richiesta non e' piu' in volo.
        assert engine.cancel(request) is False

    asyncio.run(scenario())


def test_cancel_of_a_request_that_is_not_running_does_nothing():
    assert ProsimosEngine().cancel(_request()) is False


def test_a_run_cancelled_from_outside_stays_a_plain_cancellation(monkeypatch):
    # Lo spegnimento del worker non deve sembrare un annullamento del consulente.
    engine = ProsimosEngine()

    async def scenario():
        started = asyncio.Event()
        _slow_adapter(monkeypatch, started)
        running = asyncio.create_task(engine.run(_request()))
        await started.wait()
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running

    asyncio.run(scenario())


def test_the_same_request_cannot_run_twice_at_once(monkeypatch):
    engine = ProsimosEngine()
    request = _request()

    async def scenario():
        started = asyncio.Event()
        _slow_adapter(monkeypatch, started)
        first = asyncio.create_task(engine.run(request))
        await started.wait()
        with pytest.raises(EngineError, match="gia' girando"):
            await engine.run(request)
        engine.cancel(request)
        with pytest.raises(EngineCancelled):
            await first

    asyncio.run(scenario())
