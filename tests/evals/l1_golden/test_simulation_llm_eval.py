"""SIM-23 e SIM-24b con il modello vero: quanto traduce e quanto scrive bene, in numeri.

Spento di default, perche' costa chiamate e non e' deterministico:

    DELIR_GOLDEN_EVAL=1 DELIR_LIVE_LLM=1 uv run pytest tests/evals/l1_golden/test_simulation_llm_eval.py -q -s

Ogni frase e ogni confronto di `tests/golden/simulation/` passa dal codice di
produzione (`translate`, `write`: stesso prompt, stesso schema, stessa verifica)
sul modello dei test. Il rapporto finisce in `tests/golden/reports/simulation_*.json`.

Il set e' `draft_da_validare`: si misura e si riporta, non fa fallire niente
finche' un consulente non l'ha riletto e non c'e' una baseline. Falliscono solo
le due cose che non dipendono dal giudizio: una modifica su un elemento che la
frase non nomina mai in un caso "niente da tradurre", e un testo per il cliente
che, verificato, contiene ancora una cifra fuori dai valori dei run.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict
from pathlib import Path

import pytest

from tests.evals.simulation_llm_metrics import (
    load_narrative_cases,
    load_what_if_cases,
    score_narrative,
    score_what_if,
    summarize_narrative,
    summarize_what_if,
)
from tests.live_llm import ENABLED as LIVE_LLM_ENABLED
from tests.live_llm import provider_ready

_ENABLED = os.environ.get("DELIR_GOLDEN_EVAL") == "1"

pytestmark = [
    pytest.mark.live_llm,
    pytest.mark.skipif(
        not _ENABLED or not LIVE_LLM_ENABLED or not provider_ready(),
        reason="eval della simulazione spento: serve DELIR_GOLDEN_EVAL=1, DELIR_LIVE_LLM=1 e il modello dei test (DELIR_TEST_LLM_*)",
    ),
]

REPORTS = Path(__file__).resolve().parents[2] / "golden" / "reports"


def _write(name: str, payload: dict) -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_what_if_sentences_on_the_live_model():
    from backend.simulation.whatif import SimulationWhatIfRequest, WhatIfFailed, translate

    scores, rows = [], []
    for case in load_what_if_cases():
        request = SimulationWhatIfRequest.model_validate(case.request)
        try:
            result = translate("golden-simulation", request)
        except WhatIfFailed as exc:
            score = score_what_if(case, [], None)
            rows.append({"case": case.case_id, "error": str(exc), **asdict(score)})
            scores.append(score)
            continue
        changes = [change.model_dump(exclude_none=True) for change in result.changes]
        score = score_what_if(case, changes, result.not_understood)
        scores.append(score)
        rows.append({"case": case.case_id, "changes": changes, "not_understood": result.not_understood, "rejected": result.rejected, **asdict(score)})
        if not case.expected and case.not_understood:
            # Una frase senza niente da tradurre non cambia la bozza: qui un falso positivo e' un errore, non un voto basso.
            assert not changes, f"{case.case_id}: il modello ha cambiato la bozza su una frase senza modifiche: {changes}"

    summary = summarize_what_if(scores)
    _write("simulation_what_if.json", {"summary": summary, "cases": rows})
    print("\nSIM-23 what-if:", json.dumps(summary, ensure_ascii=False))


def test_client_narrative_on_the_live_model():
    from backend.simulation.narrative import NarrativeRejected, SimulationNarrativeRequest, write

    scores, rows = [], []
    for case in load_narrative_cases():
        request = SimulationNarrativeRequest.model_validate(case.request)
        try:
            result = write("golden-simulation", request)
        except NarrativeRejected as exc:
            score = score_narrative(case, None, rejection=str(exc))
            scores.append(score)
            rows.append({"case": case.case_id, **asdict(score)})
            continue
        score = score_narrative(case, result.cited)
        scores.append(score)
        rows.append({"case": case.case_id, "text": result.text, **asdict(score)})
        # Dopo la verifica le sole cifre ammesse sono quelle dei valori dei KPI e dei nomi.
        leftover = result.text
        for allowed in [kpi.value for kpi in request.kpis] + request.names + [request.scenario_name, request.as_is_name]:
            leftover = leftover.replace(allowed, " ")
        assert not re.search(r"\d", leftover), f"{case.case_id}: cifra non verificata nel testo: {result.text}"

    summary = summarize_narrative(scores)
    _write("simulation_narrative.json", {"summary": summary, "cases": rows})
    print("\nSIM-24b testo per il cliente:", json.dumps(summary, ensure_ascii=False))
