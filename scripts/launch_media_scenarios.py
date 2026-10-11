"""Gli scenari del workspace per il video hero: AS-IS, A e B, ripetuti.

Il workspace degli scenari (SIM-14) confronta ogni alternativa con l'AS-IS
sullo stesso seed comune, con le ripetizioni e l'intervallo al 95%. Qui si
simulano davvero, con il motore del prodotto, i tre scenari del caso demo:

- AS-IS: il processo di oggi (scripts/launch_media_simulate.py);
- A: solo la delega, una finestra di autorizzazione ogni giorno;
- B: delega + richiesta che nasce completa (il To-Be della demo).

Ogni scenario gira 6 volte con seed consecutivi (come il pannello). Esce
`e2e/launch-media/data/scenarios.json` con i summary dei run.

    PYTHONPATH=. uv run python scripts/launch_media_scenarios.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from launch_media_simulate import (  # noqa: E402
    DATA,
    RESPONSABILE_TO_BE,
    SEED,
    START,
    TOTAL_CASES,
    as_is_model,
    declared,
    finite,
    to_be_model,
)

from backend.simulation.bpmn_normalizer import normalize_bpmn_for_prosimos  # noqa: E402
from backend.simulation.ir.model import SimulationModel  # noqa: E402
from backend.simulation.log_processor import activity_name_to_element_id, process_prosimos_log  # noqa: E402
from backend.simulation.models import ProsimosSimulationRequest  # noqa: E402
from backend.simulation.prosimos_adapter import run_prosimos_simulation  # noqa: E402
from backend.simulation.result_parser import with_output_files  # noqa: E402
from backend.simulation.scenario_builder import baseline_for_bpmn, build_prosimos_scenario_from_model  # noqa: E402

REPLICATIONS = 6


def delegate_only(as_is: SimulationModel) -> SimulationModel:
    """A: cambia solo la disponibilita' del responsabile (delega ogni giorno)."""
    data = as_is.model_dump(mode="json")
    data["calendars"].append({"id": "responsabile-con-delega", "name": "Autorizzazione ogni giorno (delega)", "periods": RESPONSABILE_TO_BE})
    for pool in data["pools"]:
        for resource in pool["resources"]:
            if resource["name"] == "Responsabile Acquisti":
                resource["calendar_id"] = "responsabile-con-delega"
                resource["provenance"] = {
                    **declared("francesca", note="To-Be A: delega con una finestra al giorno: assunzione del consulente."),
                    "origin": "manual",
                    "confidence": "low",
                }
    return SimulationModel.model_validate(data)


async def summary(bpmn_xml: str, model: SimulationModel, seed: int) -> dict:
    scenario = build_prosimos_scenario_from_model(bpmn_xml=bpmn_xml, model=model)
    result = with_output_files(
        await run_prosimos_simulation(
            ProsimosSimulationRequest(bpmn_xml=bpmn_xml, scenario=scenario, total_cases=TOTAL_CASES, start_date=START, seed=seed)
        )
    )
    if not result.event_log_csv:
        raise RuntimeError("Prosimos non ha restituito il log")
    values, _replay = process_prosimos_log(
        result.event_log_csv,
        normalized_bpmn_xml=bpmn_xml,
        scenario_payload=scenario.payload,
        prosimos_stats=result.payload,
        name_to_element_id=activity_name_to_element_id(bpmn_xml),
    )
    return values


async def main() -> None:
    source = (DATA / "as-is.bpmn").read_text(encoding="utf-8")
    bpmn_xml = normalize_bpmn_for_prosimos(source)
    as_is = as_is_model(baseline_for_bpmn(bpmn_xml, source_bpmn_xml=source))
    scenarios = {
        "AS-IS": ("Situazione attuale", as_is),
        "A": ("Delega giornaliera", delegate_only(as_is)),
        "B": ("Richiesta completa + delega", to_be_model(as_is)),
    }
    out = {"seed": SEED, "total_cases": TOTAL_CASES, "scenarios": []}
    for label, (name, model) in scenarios.items():
        runs = []
        for index in range(REPLICATIONS):
            values = await summary(bpmn_xml, model, SEED + index)
            runs.append({"seed": SEED + index, "summary": values})
            print(label, index + 1, f"ciclo_gg={values['cycle']['avg'] / 86400:.2f}", f"costo={values['cost']['perCase']:.1f}")
        out["scenarios"].append({"label": label, "name": name, "model": model.model_dump(mode="json"), "runs": runs})
    (DATA / "scenarios.json").write_text(json.dumps(finite(out), ensure_ascii=False, allow_nan=False), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
