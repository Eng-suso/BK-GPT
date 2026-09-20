"""Il golden set con l'estrattore vero: quanto DeliR mappa bene, in numeri.

`tests/test_golden_graph_metrics.py` verifica il tratto che deve essere esatto -
dal piano al disegno - e gira in ogni CI. Qui si misura il tratto che non puo'
esserlo: dalle interviste al piano, con l'LLM vero. Spento di default, perche'
costa chiamate e non e' deterministico:

    DELIR_GOLDEN_EVAL=1 DELIR_LIVE_LLM=1 uv run pytest tests/evals/test_golden_set.py -q -s

Per ogni caso: estrazione per fonte a testo intero, compilazione, confronto col
riferimento, verifica di provenance. Il rapporto finisce in
`tests/golden/reports/<caso>.json`.

Un caso `validated` confrontato con `tests/golden/baseline.json` fa fallire il
run se peggiora oltre la tolleranza, o se smette di essere onesto (su questo
nessuna tolleranza). Un caso `draft_da_validare` viene misurato e riportato ma
non fa fallire niente: un riferimento non ancora firmato da un consulente non e'
un metro, e usarlo come gate vorrebbe dire ottimizzare l'estrattore verso le
opinioni di chi l'ha scritto.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from backend.settings import settings
from tests.live_llm import ENABLED as LIVE_LLM_ENABLED

_ENABLED = os.environ.get("DELIR_GOLDEN_EVAL") == "1"

pytestmark = [
    pytest.mark.live_llm,
    pytest.mark.skipif(
        not _ENABLED or not LIVE_LLM_ENABLED or not settings.openai_api_key,
        reason="golden eval spento: serve DELIR_GOLDEN_EVAL=1, DELIR_LIVE_LLM=1 e OPENAI_API_KEY",
    ),
]

GOLDEN = Path(__file__).resolve().parents[1] / "golden"
REPORTS = GOLDEN / "reports"
BASELINE = GOLDEN / "baseline.json"


def _cases():
    from tests.evals.graph_metrics import load_golden_cases

    return load_golden_cases(GOLDEN)


@pytest.mark.parametrize("case", _cases() if _ENABLED else [], ids=lambda case: case.case_id)
def test_the_extractor_maps_the_golden_case(case):
    from backend.agents.plan_consolidation import llm_plan_unifier
    from backend.agents.plan_provenance import verify_plan_provenance
    from backend.agents.process_synthesis import extract_plan_from_sources
    from backend.bpmn import build_bpmn_semantic_model, semantic_model_to_bpmn_xml
    from tests.evals.graph_metrics import compare, parse_bpmn, plan_shape, regressions

    sources = case.source_texts()
    # Lo stesso percorso della sintesi in produzione, consolidamento compreso:
    # misurare l'estrattore senza l'unificazione dei doppioni vorrebbe dire
    # misurare un piano che nessun consulente vede.
    extraction = extract_plan_from_sources(case.process_name, sources, unifier=llm_plan_unifier())
    assert extraction.process is not None, (
        f"{case.case_id}: nessun piano estratto ({'; '.join(extraction.failures)})"
    )

    model = build_bpmn_semantic_model(
        process_id=f"Process_{case.case_id}",
        process_name=case.process_name,
        process=extraction.process,
    )
    metrics = compare(parse_bpmn(semantic_model_to_bpmn_xml(model)), case)
    provenance = verify_plan_provenance(extraction.process, sources)

    report = {
        **metrics.as_dict(),
        "status": case.status,
        "llm_calls": extraction.llm_calls,
        "extraction_failures": extraction.failures,
        "provenance": provenance.summary(),
        "compiler_warnings": model.model_warnings,
        "plan": plan_shape(extraction.process.model_dump(mode="json")),
        "consolidation": (
            extraction.consolidation.as_log_entry() if extraction.consolidation else None
        ),
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / f"{case.case_id}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if case.status != "validated":
        pytest.skip(f"{case.case_id}: riferimento non ancora validato, misurato e non usato come gate")

    baseline = json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.exists() else {}
    if case.case_id not in baseline:
        pytest.skip(f"{case.case_id}: nessuna baseline registrata, il rapporto la puo' diventare")

    found = regressions(report, baseline[case.case_id])
    assert not found, "regressioni sul golden set:\n" + "\n".join(found)
