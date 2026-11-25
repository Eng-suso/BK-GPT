"""VAL-01: le risposte del backend vero per l'e2e del rifiuto all'import.

L'e2e simula il backend; il rifiuto lo produce il codice del prodotto, cosi' il
test mostra al consulente esattamente cio' che leggerebbe. Rigenerare dopo un
cambio della verifica, dell'import o del template:

    PYTHONPATH=. uv run python e2e/fixtures/val-01/generate.py

- ``academic.*``: lo scenario SIMOD di AcademicCredentials scoperto in G3, con il
  ciclo a uscita 0 (l'editor non lo rappresenta: lo legge il server);
- ``loop.*``: un file piccolo che l'editor legge da solo, con lo stesso difetto;
  ``loop-fixed.import.json`` e' lo stesso file con l'uscita riaperta.
"""

from __future__ import annotations

import copy
import json
from dataclasses import asdict
from pathlib import Path

from backend.schemas.api import ApiEnvelope, ApiError, ApiMeta
from backend.schemas.simulation_model import ProsimosImportNote, ProsimosImportResponse
from backend.schemas.workspace import BpmnModelResponse
from backend.simulation.ir.from_prosimos import import_prosimos
from backend.simulation.ir.soundness import UnsoundProcessError
from backend.simulation.service import scenario_template_for_model

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).parent
ACADEMIC = ROOT / "tests" / "simulation" / "benchmark" / "g3" / "discovered" / "AcademicCredentials_diff"


def _write(name: str, value: object) -> None:
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def _template(bpmn: str) -> object:
    template = scenario_template_for_model(
        bpmn_model=BpmnModelResponse(id="val-model", process_id="val-process", name="Processo", xml=bpmn),
        current_bpmn_xml=None,
    )
    return template.model_dump(mode="json")


def _refusal(scenario: dict, bpmn: str) -> object:
    """Il corpo del 400 che ``backend/api/errors.py`` scrive per ``UnsoundProcessError``."""
    try:
        import_prosimos(scenario, bpmn)
    except UnsoundProcessError as exc:
        return ApiEnvelope(
            ok=False,
            data=None,
            error=ApiError(
                code="process_cannot_finish", message=str(exc), detail=exc.detail,
                request_id="val-01", origin="server", retryable=False,
            ),
            meta=ApiMeta(request_id="val-01", duration_ms=1),
        ).model_dump(mode="json")
    raise SystemExit("lo scenario doveva essere rifiutato")


def _accepted(scenario: dict, bpmn: str) -> object:
    result = import_prosimos(scenario, bpmn)
    return ProsimosImportResponse(
        bpmn_model_id="val-model",
        model=result.model,
        notes=[ProsimosImportNote(**asdict(note)) for note in result.notes],
        simod=result.simod,
    ).model_dump(mode="json")


def main() -> None:
    academic_bpmn = (ACADEMIC / "AcademicCredentials.bpmn").read_text(encoding="utf-8")
    academic = json.loads((ACADEMIC / "AcademicCredentials.json").read_text(encoding="utf-8"))
    _write("academic.template.json", _template(academic_bpmn))
    _write("academic.refusal.json", _refusal(academic, academic_bpmn))

    loop_bpmn = (HERE / "loop.bpmn").read_text(encoding="utf-8")
    loop = json.loads((HERE / "loop.json").read_text(encoding="utf-8"))
    _write("loop.template.json", _template(loop_bpmn))
    _write("loop.refusal.json", _refusal(loop, loop_bpmn))
    fixed = copy.deepcopy(loop)
    fixed["gateway_branching_probabilities"][0]["probabilities"] = [
        {"path_id": "F_again", "value": 0.2}, {"path_id": "F_done", "value": 0.8},
    ]
    _write("loop-fixed.json", fixed)
    _write("loop-fixed.import.json", _accepted(fixed, loop_bpmn))


if __name__ == "__main__":
    main()
