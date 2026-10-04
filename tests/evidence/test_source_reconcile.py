"""P1.13: il confronto fra le affermazioni di file diversi.

Il modello qui e' finto: il test controlla cosa il codice fa della risposta -
quali coppie tiene, come le regole indeboliscono una divergenza - non quanto il
modello sia bravo (quello e' il lavoro degli eval).
"""

from __future__ import annotations

import pytest

from backend.workspace_services.evidence import reconcile as reconcile_module
from backend.workspace_services.evidence.reconcile import (
    MAX_INPUT_CHARS,
    Reconciliation,
    reconcile_claims,
    reconcile_prompt_version,
    render_claims,
)

NEW = [
    {"id": 11, "statement": "Il CFO approva gli ordini sopra i 30.000 EUR.", "source_id": "src-b", "source_name": "procedura.pdf"},
    {"id": 12, "statement": "Le fatture si registrano in SAP.", "source_id": "src-b", "source_name": "procedura.pdf"},
]
EXISTING = [
    {"id": 1, "statement": "Gli ordini oltre 50.000 EUR li approva il CFO.", "source_id": "src-a", "source_name": "intervista.docx"},
    {"id": 2, "statement": "La registrazione delle fatture avviene in SAP.", "source_id": "src-a", "source_name": "intervista.docx"},
]


@pytest.fixture()
def model(monkeypatch):
    def install(pairs: list[dict], seen: dict | None = None, *, forbid: bool = False):
        def run(**kwargs):
            if forbid:
                raise AssertionError("niente da confrontare, niente da pagare")
            if seen is not None:
                seen.update(kwargs)
            return Reconciliation.model_validate({"pairs": pairs})

        monkeypatch.setattr(reconcile_module, "llm_run", run)

    return install


def _pair(new: int, existing: int, relation: str, **extra) -> dict:
    return {"new": new, "existing": existing, "relation": relation, "explanation": "spiegazione", **extra}


def test_same_fact_said_twice_is_a_corroboration_and_different_thresholds_a_divergence(model):
    seen: dict = {}
    model(
        [
            _pair(1, 1, "diverge", divergence_type="incompatible"),
            _pair(2, 2, "same"),
        ],
        seen,
    )
    result = reconcile_claims(NEW, EXISTING)

    by_claim = {relation.claim_id: relation for relation in result.relations}
    assert by_claim[11].kind == "divergence"
    assert by_claim[11].other_claim_id == 1
    assert by_claim[11].divergence_type == "incompatible"
    assert by_claim[12].kind == "corroboration"
    assert by_claim[12].other_claim_id == 2
    assert result.prompt_version == reconcile_prompt_version()
    assert seen["prompt_version"] == reconcile_prompt_version()
    assert "[E1] (intervista.docx)" in seen["messages"][1].content


def test_the_rules_only_weaken_what_the_model_declares(model):
    model(
        [
            # ambiti diversi: non e' un'incompatibilita'
            _pair(1, 1, "diverge", divergence_type="incompatible", new_scope="sede di Parma", existing_scope="sede di Milano"),
            # una parte dichiara di non sapere: e' una lacuna
            _pair(2, 2, "diverge", divergence_type="incompatible", unknown_side="existing"),
        ]
    )
    result = reconcile_claims(NEW, EXISTING)

    by_claim = {relation.claim_id: relation for relation in result.relations}
    assert by_claim[11].declared_type == "incompatible"
    assert by_claim[11].divergence_type == "scope_difference"
    assert by_claim[11].reasons
    assert by_claim[12].divergence_type == "knowledge_gap"


def test_pairs_that_point_nowhere_or_inside_the_same_file_are_dropped(model):
    same_file = [{**EXISTING[0], "source_id": "src-b"}]
    model([_pair(9, 1, "same"), _pair(1, 7, "same"), _pair(1, 1, "same"), _pair(1, 1, "same")])

    result = reconcile_claims(NEW, same_file)

    assert result.relations == []
    assert result.discarded == 4


def test_a_repeated_pair_counts_once(model):
    model([_pair(2, 2, "same"), _pair(2, 2, "same")])
    assert len(reconcile_claims(NEW, EXISTING).relations) == 1


def test_nothing_to_compare_costs_nothing(model):
    model([], forbid=True)
    assert reconcile_claims([], EXISTING).relations == []
    assert reconcile_claims(NEW, []).relations == []


def test_existing_claims_past_the_budget_are_left_out_and_counted():
    long = "x" * 500
    existing = [
        {"id": n, "statement": long, "source_id": "src-a", "source_name": "a.pdf"}
        for n in range(MAX_INPUT_CHARS // 400)
    ]
    rendered, shown_new, shown_existing, left_out = render_claims(NEW, existing)

    assert len(rendered) <= MAX_INPUT_CHARS
    assert len(shown_new) == len(NEW)
    assert left_out > 0
    assert len(shown_existing) + left_out == len(existing)
