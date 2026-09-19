"""Il loop di conformita' con il modello vero, sui casi del golden set.

`tests/test_evidence_canvas_conformance_e2e.py` verifica l'harness con un
estrattore e un revisore finti. Qui gira la stessa catena con l'LLM vero, dallo
stato che ha rotto il caso Esaote - un piano vuoto nato prima delle interviste -
fino al canvas verificato:

    piano V1 vuoto + interviste -> «Genera BPMN» -> sintesi per fonte -> disegno
    -> revisore (deterministico + agente per fonte) -> riparazione -> riverifica

Spento di default, perche' costa chiamate e non e' deterministico:

    DELIR_AGENT_EVAL=1 uv run pytest tests/evals/test_conformance_eval.py -q -s

Cosa fa fallire, senza tolleranza: un rilievo dei layer deterministici. Canvas
diverso dal piano, piano non corrente, documento di review diverso dal piano
sono difetti del runtime, non giudizi del modello. Cio' che il revisore trova
sulle fonti si misura e finisce nel rapporto
(`tests/golden/reports/<caso>.conformance.json`): e' la misura di quanto
l'estrattore e' fedele, non un gate finche' i casi non sono `validated`.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import pytest

from backend.settings import settings

_ENABLED = os.environ.get("DELIR_AGENT_EVAL") == "1"

pytestmark = pytest.mark.skipif(
    not _ENABLED
    or not settings.openai_api_key
    or not all((settings.workspace_database_url, settings.canonical_database_url)),
    reason="eval di conformita' spento: servono DELIR_AGENT_EVAL=1, OPENAI_API_KEY e le DSN",
)

GOLDEN = Path(__file__).resolve().parents[1] / "golden"
REPORTS = GOLDEN / "reports"
DETERMINISTIC_LAYERS = {"plan_currency", "canvas_plan", "review_plan"}


def _cases():
    from tests.evals.graph_metrics import load_golden_cases

    return load_golden_cases(GOLDEN)


@pytest.mark.parametrize("case", _cases() if _ENABLED else [], ids=lambda case: case.case_id)
def test_the_conformance_loop_on_a_golden_case(case):
    from backend import workspace_database as wd
    from backend.agents.process_snapshot import build_process_snapshot
    from backend.agents.scope_guard import bind_active_scope
    from backend.process_understanding import ProcessUnderstanding
    from backend.schemas.chat import ProcessChatScope
    from backend.security import reset_current_tenant_id, set_current_tenant_id
    from backend.toolsets.process_memory import manage_process_evidence
    from backend.workspace_services.bpmn_draft import generate_verified_bpmn_draft

    token = set_current_tenant_id(f"t-conformance-eval-{uuid.uuid4().hex[:8]}")
    try:
        client = wd.create_client(name=f"Eval {case.case_id}")
        project = wd.create_project(client_id=client["id"], name=f"Eval {uuid.uuid4().hex[:6]}")
        process = wd.create_process(project_id=project["id"], name=case.process_name)
        wd.prepare_bpmn_review(
            bpmn_model_id=process["bpmn_model_id"],
            process_description="Generare il BPMN dalle evidenze disponibili.",
            process_understanding=ProcessUnderstanding(title=case.process_name).model_dump(mode="json"),
        )
        scope = ProcessChatScope(type="process", project_id=project["id"], process_id=process["id"])
        with bind_active_scope(scope):
            for source in case.source_texts():
                manage_process_evidence.invoke(
                    {
                        "operation": "save_interview",
                        "project_id": project["id"],
                        "process_id": process["id"],
                        "title": source["name"],
                        "raw_content": source["content"],
                        "summary": source["name"],
                        "participants": [],
                        "entities": [],
                    }
                )
            result = generate_verified_bpmn_draft(process["id"])

        from tests.evals.graph_metrics import plan_shape

        snapshot = build_process_snapshot(process["id"])
        report = result.conformance
        REPORTS.mkdir(parents=True, exist_ok=True)
        (REPORTS / f"{case.case_id}.conformance.json").write_text(
            json.dumps(
                {
                    "status": result.status,
                    "reason_code": result.reason_code,
                    "metrics": result.metrics,
                    "repairs": result.conformance_repairs,
                    "plan": (
                        plan_shape(snapshot.process_understanding)
                        if snapshot and snapshot.process_understanding
                        else None
                    ),
                    "conformance": report.model_dump(mode="json") if report else None,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        assert result.status == "drafted", f"{result.reason_code}: {result.reason} {result.issues}"
        assert snapshot is not None and snapshot.plan_is_current
        assert (snapshot.process_understanding or {}).get("steps"), "piano senza attivita'"
        assert report is not None and report.llm_audit == "done", report.llm_audit_note if report else None
        runtime_defects = [item for item in report.findings if item.layer in DETERMINISTIC_LAYERS]
        assert runtime_defects == [], [item.message for item in runtime_defects]
    finally:
        reset_current_tenant_id(token)
