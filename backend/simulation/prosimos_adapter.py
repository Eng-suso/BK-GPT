from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime

import httpx

from backend.settings import settings
from backend.simulation.engine import EngineError
from backend.simulation.models import ProsimosSimulationRequest, ProsimosSimulationResult
from backend.simulation.validation import validate_simulation_bpmn

logger = logging.getLogger(__name__)

#: Il runner DeliR gira su Prosimos 2.x. La 1.2.6 accetta regole di routing e
#: attributi d'evento e li ignora: un run "riuscito" li avrebbe simulati male.
MIN_ENGINE_MAJOR = 2


class ProsimosError(EngineError):
    """Il runner Prosimos non ha eseguito il run."""


def _auth_headers() -> dict[str, str]:
    token = settings.prosimos_api_token
    return {"Authorization": f"Bearer {token}"} if token else {}


def _engine_major(version: object) -> int | None:
    match = re.match(r"\s*(\d+)", str(version or ""))
    return int(match.group(1)) if match else None


async def run_prosimos_simulation(
    request: ProsimosSimulationRequest,
) -> ProsimosSimulationResult:
    try:
        validate_simulation_bpmn(request.bpmn_xml)
    except ValueError as exc:
        raise ProsimosError(str(exc)) from exc
    base_url = settings.prosimos_base_url.rstrip("/")
    simulate_url = f"{base_url}/api/simulate"
    start = request.start_date or datetime.now(UTC).isoformat()
    # inlineLog: il log torna nella stessa risposta, senza un secondo GET che con
    # piu' repliche del runner potrebbe finire su un container senza il file.
    form = {"startDate": start, "numProcesses": str(request.total_cases), "inlineLog": "1"}
    if request.seed is not None:
        form["seed"] = str(request.seed)

    try:
        async with httpx.AsyncClient(timeout=settings.prosimos_timeout_seconds) as client:
            response = await client.post(
                simulate_url,
                data=form,
                headers=_auth_headers(),
                files={
                    "modelFile": ("process.bpmn", request.bpmn_xml.encode("utf-8"), "application/xml"),
                    "simScenarioFile": (
                        "scenario.json",
                        json.dumps(request.scenario.payload, ensure_ascii=False).encode("utf-8"),
                        "application/json",
                    ),
                },
            )
    except httpx.TimeoutException as exc:
        raise ProsimosError(
            f"Prosimos non ha risposto entro {settings.prosimos_timeout_seconds:g} secondi: "
            "riduci i casi o l'orizzonte e rilancia."
        ) from exc
    except httpx.HTTPError as exc:
        raise ProsimosError(
            f"Prosimos non raggiungibile su {base_url}. Avvia il runner (ops/prosimos/runner)."
        ) from exc

    if response.status_code >= 400:
        raise ProsimosError(
            f"Prosimos ha rifiutato la simulazione ({response.status_code}): {response.text[:500]}"
        )

    try:
        payload = response.json()
    except ValueError:
        payload = {"raw": response.text}

    if not isinstance(payload, dict):
        payload = {"result": payload}

    # SIM-08: un motore che non conosce le fasce le ignorerebbe e simulerebbe
    # arrivi diversi da quelli chiesti, senza dirlo.
    bands = request.scenario.payload.get("delir_arrival_bands") or []
    if bands and payload.get("ArrivalBands") != len(bands):
        raise ProsimosError(
            "Il motore non applica le fasce degli arrivi: serve il runner DeliR (ops/prosimos/runner)."
        )
    months = request.scenario.payload.get("delir_arrival_months") or {}
    if months and payload.get("ArrivalMonths") != len(months):
        raise ProsimosError(
            "Il motore non applica il ritmo degli arrivi per mese: serve il runner DeliR (ops/prosimos/runner)."
        )
    # SIM-33b: lo stesso per le durate che cambiano con l'ora d'inizio.
    windows = request.scenario.payload.get("delir_duration_windows") or {}
    if windows and payload.get("DurationWindows") != len(windows):
        raise ProsimosError(
            "Il motore non applica le durate per fascia oraria: serve il runner DeliR (ops/prosimos/runner)."
        )

    # Dopo i controlli specifici, il motore stesso: un servizio che non dichiara
    # una versione 2.x non e' il runner DeliR e ignorerebbe parti dello scenario.
    version = payload.get("EngineVersion")
    major = _engine_major(version)
    if major is None or major < MIN_ENGINE_MAJOR:
        raise ProsimosError(
            f"Il motore su {base_url} non e' il runner DeliR (Prosimos {version or 'versione non dichiarata'}): "
            "servono Prosimos 2.x e il runner di ops/prosimos/runner."
        )

    # Seed e data di inizio insieme rifanno lo stesso log: senza una data nella
    # richiesta si usa "adesso", quindi va conservata quella effettivamente usata.
    payload.setdefault("StartDate", start)
    inline = payload.pop("EventLogCsv", None)
    event_log_csv = inline if isinstance(inline, str) and inline else await _fetch_event_log(base_url, payload)
    if not event_log_csv:
        # Senza log non ci sono KPI: un run "completato" vuoto ingannerebbe il consulente.
        raise ProsimosError("Il motore ha finito la simulazione ma il log degli eventi non e' arrivato: rilanciala.")

    return ProsimosSimulationResult(
        payload=_normalize_prosimos_payload(payload),
        event_log_csv=event_log_csv,
    )


async def _fetch_event_log(base_url: str, payload: dict) -> str | None:
    """Scarica il log da ``GET {base}/api/simulationFile`` (runner senza ``inlineLog``).

    ``None`` se il file non c'e' o non si scarica; il chiamante decide.
    """
    filename = payload.get("LogsFilename") or payload.get("logFile")
    if not isinstance(filename, str) or not filename:
        logger.warning("Prosimos: risposta senza log in linea e senza LogsFilename")
        return None
    try:
        async with httpx.AsyncClient(timeout=settings.prosimos_timeout_seconds) as client:
            response = await client.get(
                f"{base_url}/api/simulationFile",
                params={"fileName": filename},
                headers=_auth_headers(),
            )
    except httpx.HTTPError:
        logger.warning("Prosimos: download del log %s fallito", filename, exc_info=True)
        return None
    if response.status_code >= 400:
        logger.warning("Prosimos: download del log %s rifiutato (%s)", filename, response.status_code)
        return None
    return response.text


_STATISTIC_KEYS = (
    "ResourceUtilization",
    "IndividualTaskStatistics",
    "OverallScenarioStatistics",
)


def _normalize_prosimos_payload(payload: dict) -> dict:
    """Prosimos returns statistics as multiply json-encoded strings; decode them
    so the UI and downstream comparison get real objects."""
    normalized = dict(payload)
    for key in _STATISTIC_KEYS:
        if key in normalized:
            normalized[key] = _deep_json_decode(normalized[key])
    return normalized


def _deep_json_decode(value: object, _depth: int = 0) -> object:
    if _depth >= 5 or not isinstance(value, str):
        return value
    try:
        return _deep_json_decode(json.loads(value), _depth + 1)
    except (ValueError, TypeError):
        return value
