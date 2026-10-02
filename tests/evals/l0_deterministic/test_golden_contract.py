"""Il riferimento del golden set dice il vero sulle sue fonti.

Le metriche sull'estrattore valgono quanto il riferimento con cui lo misurano.
Una citazione ritoccata a memoria, un'attivita' disegnata senza che nessuno la
dica, un conflitto ricordato male: il metro e' storto, e l'estrattore viene
premiato o punito per le opinioni di chi ha scritto il caso.

Qui si verifica, senza modello e a ogni PR, cio' che si puo' verificare alla
lettera: ogni citazione sta davvero nella sua fonte, e in un caso v2 ogni
attivita' e decisione obbligatoria e' legata a un passo che la dice.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.evals.graph_metrics import (
    LABEL_MATCH_THRESHOLD,
    ReferenceCase,
    label_score,
    load_golden_cases,
)

GOLDEN = Path(__file__).resolve().parents[2] / "golden"
CASES = load_golden_cases(GOLDEN)
V2_CASES = [case for case in CASES if case.schema_version >= 2]

_SPACES = re.compile(r"\s+")


def _flat(text: str) -> str:
    """Il testo a spazi normalizzati: una citazione puo' andare a capo diversamente."""
    return _SPACES.sub(" ", text).strip()


def _quotes(case: ReferenceCase) -> list[tuple[str, str, str]]:
    return [
        *((f"evidenza di {item.element}", item.source, item.quote) for item in case.evidence_bindings),
        *(
            (f"claim {claim.id}", quote.source, quote.quote)
            for claim in case.expected_claims
            for quote in claim.evidence
        ),
        *(
            (f"conflitto {conflict.id}", quote.source, quote.quote)
            for conflict in case.expected_conflicts
            for quote in conflict.positions
        ),
    ]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.case_id)
def test_every_quote_is_in_its_source_word_for_word(case: ReferenceCase):
    texts = {source["name"]: _flat(source["content"]) for source in case.source_texts()}

    missing = [
        f"{what}: «{quote}» non e' in {source}"
        for what, source, quote in _quotes(case)
        if _flat(quote) not in texts[source]
    ]

    assert not missing, "\n".join(missing)


@pytest.mark.parametrize("case", V2_CASES, ids=lambda case: case.case_id)
def test_every_required_element_of_a_v2_case_has_its_evidence(case: ReferenceCase):
    bound = {binding.element for binding in case.evidence_bindings}
    required = [item.id for item in case.activities if item.required] + list(case.gateways)

    unbound = [element for element in required if element not in bound]

    assert not unbound, f"{case.case_id}: senza un passo delle fonti che li dica: {unbound}"


@pytest.mark.parametrize("case", V2_CASES, ids=lambda case: case.case_id)
def test_a_v2_case_states_the_facts_the_process_rests_on(case: ReferenceCase):
    assert case.expected_claims, f"{case.case_id}: un caso v2 dichiara i suoi claim attesi"



@pytest.mark.parametrize("case", V2_CASES, ids=lambda case: case.case_id)
def test_a_claim_or_conflict_written_in_its_own_words_is_found(case: ReferenceCase):
    """Alias che nemmeno il testo del claim soddisfa non ritroverebbero nessun piano."""
    unreachable = [
        *(
            f"claim {claim.id}"
            for claim in case.expected_claims
            if label_score(claim.text, claim.aliases) < LABEL_MATCH_THRESHOLD
        ),
        *(
            f"conflitto {conflict.id}"
            for conflict in case.expected_conflicts
            if label_score(conflict.about, conflict.detected_by_aliases) < LABEL_MATCH_THRESHOLD
        ),
    ]

    assert not unreachable, f"{case.case_id}: alias irraggiungibili: {unreachable}"


def test_every_golden_case_is_on_the_v2_contract():
    """Un caso v1 misura solo il disegno: evidenze, claim e conflitti resterebbero fuori."""
    v1 = [case.case_id for case in CASES if case.schema_version < 2]

    assert not v1, f"casi ancora sul contratto v1: {v1}"
