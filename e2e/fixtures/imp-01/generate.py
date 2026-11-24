"""IMP-01: le risposte del backend vero per Procure_to_Pay, usate dall'e2e.

L'e2e simula il backend; queste risposte le produce il codice del prodotto, cosi'
il test mostra al consulente esattamente cio' che vedrebbe. Rigenerare dopo un
cambio dell'import o del template (serve lo stack: ``scripts/vpt_stack.sh``):

    eval "$(scripts/vpt_stack.sh env)"
    PYTHONPATH=. uv run python e2e/fixtures/imp-01/generate.py
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from backend.schemas.simulation_model import ProsimosImportNote, ProsimosImportResponse
from backend.schemas.workspace import BpmnModelResponse
from backend.simulation.ir.from_prosimos import import_prosimos
from backend.simulation.service import scenario_template_for_model

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "datasets" / "extraneous-delays" / "inputs" / "synthetic" / "Procure_to_Pay"
HERE = Path(__file__).parent


def main() -> None:
    bpmn = SOURCE.with_suffix(".bpmn").read_text(encoding="utf-8")
    scenario = json.loads(SOURCE.with_suffix(".json").read_text(encoding="utf-8"))
    template = scenario_template_for_model(
        bpmn_model=BpmnModelResponse(id="imp-model", process_id="imp-process", name="Procure to Pay", xml=bpmn),
        current_bpmn_xml=None,
    )
    result = import_prosimos(scenario, bpmn)
    imported = ProsimosImportResponse(
        bpmn_model_id="imp-model",
        model=result.model,
        notes=[ProsimosImportNote(**asdict(note)) for note in result.notes],
        simod=result.simod,
    )
    for name, value in (("template", template), ("import", imported)):
        path = HERE / f"procure-to-pay.{name}.json"
        path.write_text(json.dumps(value.model_dump(mode="json"), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
