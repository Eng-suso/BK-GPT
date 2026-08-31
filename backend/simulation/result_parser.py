from __future__ import annotations

from typing import Any

from backend.simulation.models import ProsimosSimulationResult


def with_output_files(result: ProsimosSimulationResult) -> ProsimosSimulationResult:
    files: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, str) and value.lower().endswith((".csv", ".json", ".xes")):
            if value not in files:
                files.append(value)

    visit(result.payload)
    return ProsimosSimulationResult(
        payload=result.payload,
        outputs=files,
        event_log_csv=result.event_log_csv,
    )
