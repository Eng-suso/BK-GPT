"""Il golden set dei compiti LLM della simulazione regge, e le sue metriche dicono il vero.

Gira in ogni CI, senza modello. Il run che misura il modello vero e'
`tests/evals/l1_golden/test_simulation_llm_eval.py`.
"""

from __future__ import annotations

import re

import pytest

from backend.simulation.narrative import NarrativeDraft, SimulationNarrativeRequest, verify
from backend.simulation.whatif import SimulationWhatIfRequest, WhatIfTranslation, parse
from tests.evals.simulation_llm_metrics import (
    load_narrative_cases,
    load_what_if_cases,
    same_change,
    score_narrative,
    score_what_if,
    summarize_narrative,
    summarize_what_if,
)

WHAT_IF = load_what_if_cases()
NARRATIVE = load_narrative_cases()


def _as_model_output(change: dict, request: SimulationWhatIfRequest) -> dict:
    """La risposta che il modello dovrebbe dare per ottenere questa modifica."""
    activities = [a.id for a in request.activities]
    resources = [r.id for r in request.resources]
    kind = change["kind"]
    if kind in ("resource_units", "resource_cost"):
        target = f"R{resources.index(change['resource_id'])}"
        value = change["units"] if kind == "resource_units" else change["cost_per_hour"]
        return {"kind": kind, "target": target, "mode": "set", "value": value}
    if kind == "demand":
        return {"kind": kind, "target": "", "mode": "factor", "value": change["factor"]}
    target = f"A{activities.index(change['element_id'])}"
    if kind == "skip_activity":
        return {"kind": kind, "target": target, "mode": "percent", "value": change["percent"]}
    if change.get("factor") is not None:
        return {"kind": kind, "target": target, "mode": "factor", "value": change["factor"]}
    return {"kind": kind, "target": target, "mode": "set", "value": change["mean_minutes"]}


def test_the_what_if_set_covers_both_languages_and_every_kind():
    assert {case.language for case in WHAT_IF} == {"it", "en"}
    kinds = {change["kind"] for case in WHAT_IF for change in case.expected}
    assert kinds == {"resource_units", "activity_duration", "skip_activity", "demand", "resource_cost"}
    assert any(case.not_understood and not case.expected for case in WHAT_IF)
    assert len({case.case_id for case in WHAT_IF}) == len(WHAT_IF)


@pytest.mark.parametrize("case", WHAT_IF, ids=lambda case: case.case_id)
def test_every_expected_answer_is_one_the_code_accepts(case):
    """Se il modello rispondesse esattamente cosi', `parse` darebbe le modifiche attese: il set non chiede l'impossibile."""
    request = SimulationWhatIfRequest.model_validate(case.request)
    answer = WhatIfTranslation.model_validate({
        "changes": [_as_model_output(change, request) for change in case.expected],
        "not_understood": "qualcosa" if case.not_understood else "",
    })

    result = parse(answer, request)

    assert result.rejected == 0
    actual = [change.model_dump(exclude_none=True) for change in result.changes]
    assert score_what_if(case, actual, result.not_understood).exact


def test_what_if_metrics_count_extra_missing_and_tolerance():
    case = next(c for c in WHAT_IF if c.case_id == "it-due-modifiche")
    near = {"kind": "activity_duration", "element_id": "T_pay", "factor": 0.505}
    extra = {"kind": "demand", "factor": 1.1}

    score = score_what_if(case, [near, extra], None)

    assert (score.true_positive, score.false_positive, score.false_negative) == (1, 1, 1)
    assert not score.exact
    assert same_change({"kind": "demand", "factor": 1.2}, {"kind": "demand", "factor": 1.21})
    assert not same_change({"kind": "demand", "factor": 1.2}, {"kind": "demand", "factor": 1.3})
    summary = summarize_what_if([score])
    assert summary["precision"] == 0.5 and summary["recall"] == 0.5 and summary["exact_rate"] == 0


def test_saying_nothing_was_understood_matters():
    case = next(c for c in WHAT_IF if c.case_id == "it-niente-da-tradurre")

    assert score_what_if(case, [], "rendere snello").exact
    assert not score_what_if(case, [], None).exact


@pytest.mark.parametrize("case", NARRATIVE, ids=lambda case: case.case_id)
def test_every_narrative_case_is_a_valid_request_with_coherent_expectations(case):
    request = SimulationNarrativeRequest.model_validate(case.request)
    verdicts = {f"K{i + 1}": kpi.verdict for i, kpi in enumerate(request.kpis)}

    # Si chiede di citare solo cio' che e' certo, e "incerto" vuol dire proprio incerto.
    assert all(verdicts[k] in ("better", "worse") for k in case.must_cite)
    assert all(verdicts[k] == "unclear" for k in case.uncertain)
    # Un testo che cita i KPI richiesti senza cifre sue passa la verifica.
    text = " ".join(f"Cambia [{k}]." for k in case.must_cite) or "Nessuna differenza certa."
    assert verify(NarrativeDraft(text=text), request).cited == case.must_cite


def test_the_narrative_set_has_both_languages_and_names_with_digits():
    requests = [SimulationNarrativeRequest.model_validate(case.request) for case in NARRATIVE]
    assert {r.language for r in requests} == {"it", "en"}
    assert any(re.search(r"\d", name) for r in requests for name in r.names)


def test_narrative_metrics_count_rejections_and_missing_citations():
    case = next(c for c in NARRATIVE if c.case_id == "it-piu-veloce-piu-caro")

    ok = score_narrative(case, ["K1", "K3", "K4"])
    partial = score_narrative(case, ["K1"])
    rejected = score_narrative(case, None, rejection="numeri non verificabili")

    assert ok.missing_citations == [] and partial.missing_citations == ["K3"]
    summary = summarize_narrative([ok, partial, rejected])
    assert summary["verified_rate"] == pytest.approx(2 / 3)
    # 6 citazioni richieste, 3 trovate: l'extra K4 non conta, il testo rifiutato non cita niente.
    assert summary["citation_recall"] == pytest.approx(3 / 6)
