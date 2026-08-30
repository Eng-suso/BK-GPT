from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import httpx

from backend.settings import settings
from backend.simulation.models import ProsimosSimulationRequest, ProsimosSimulationResult


class ProsimosError(RuntimeError):
    pass


async def run_prosimos_simulation(
    request: ProsimosSimulationRequest,
) -> ProsimosSimulationResult:
    base_url = settings.prosimos_base_url.rstrip("/")
    simulate_url = f"{base_url}/api/simulate"
    start = request.start_date or datetime.now(UTC).isoformat()

    with tempfile.TemporaryDirectory(prefix="delir-prosimos-") as tmp_dir:
        tmp_path = Path(tmp_dir)
        bpmn_path = tmp_path / "process.bpmn"
        scenario_path = tmp_path / "scenario.json"
        bpmn_path.write_text(request.bpmn_xml, encoding="utf-8")
        scenario_path.write_text(
            json.dumps(request.scenario.payload, ensure_ascii=False),
            encoding="utf-8",
        )

        try:
            async with httpx.AsyncClient(timeout=settings.prosimos_timeout_seconds) as client:
                with bpmn_path.open("rb") as bpmn_file, scenario_path.open("rb") as scenario_file:
                    response = await client.post(
                        simulate_url,
                        data={
                            "startDate": start,
                            "numProcesses": str(request.total_cases),
                        },
                        files={
                            "modelFile": ("process.bpmn", bpmn_file, "application/xml"),
                            "simScenarioFile": (
                                "scenario.json",
                                scenario_file,
                                "application/json",
                            ),
                        },
                    )
        except httpx.HTTPError as exc:
            raise ProsimosError(
                f"Prosimos non raggiungibile su {base_url}. Avvia prosimos-microservice."
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

    return ProsimosSimulationResult(payload=_normalize_prosimos_payload(payload))


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
