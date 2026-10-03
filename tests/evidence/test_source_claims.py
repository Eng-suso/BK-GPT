"""P1.12: le affermazioni di un file caricato, ognuna legata alla sua porzione.

Il modello qui e' finto: il test controlla cosa il codice fa della risposta,
non quanto il modello sia bravo (quello e' il lavoro degli eval).
"""

from __future__ import annotations

import pytest

from backend.workspace_services.evidence import claims as claims_module
from backend.workspace_services.evidence.claims import (
    MAX_INPUT_CHARS,
    ClaimExtraction,
    claims_prompt_version,
    extract_claims,
    render_segments,
)

SEGMENTS = [
    {"ordinal": 0, "ref": "§1", "text": "# Procedura acquisti"},
    {"ordinal": 1, "ref": "§2", "text": "Il CFO approva gli ordini sopra i 30.000 EUR. Sotto, approva il buyer."},
    {"ordinal": 2, "ref": "R4", "text": "ordine: O-2; importo: 45000; approvatore: CFO"},
]


@pytest.fixture()
def model(monkeypatch):
    """Il gateway finto: risponde con `answer` e ricorda cosa ha ricevuto."""

    def install(answer: dict | None = None, seen: dict | None = None, *, forbid: bool = False):
        def run(**kwargs):
            if forbid:
                raise AssertionError("niente da leggere, niente da pagare")
            if seen is not None:
                seen.update(kwargs)
            return ClaimExtraction.model_validate(answer)

        monkeypatch.setattr(claims_module, "llm_run", run)

    return install


def _claim(statement: str, segment: int, quote: str) -> dict:
    return {"statement": statement, "segment": segment, "quote": quote}


def test_every_claim_is_tied_to_the_segment_it_cites(model):
    seen: dict = {}
    model(
        {
            "claims": [
                _claim(
                    "Gli ordini sopra i 30.000 EUR li approva il CFO.",
                    1,
                    "Il CFO approva gli ordini sopra i 30.000 EUR.",
                )
            ]
        },
        seen,
    )
    result = extract_claims(SEGMENTS, source_name="procedura.md")

    [claim] = result.claims
    assert claim.segment_ordinal == 1
    assert claim.anchor_ref == "§2"
    assert claim.quote_verified is True
    # Il compito e la versione del prompt arrivano al gateway (L5).
    assert seen["task"].value == "source_claims"
    assert seen["prompt_version"] == claims_prompt_version() == result.prompt_version
    assert "[S1] (§2) Il CFO approva" in seen["messages"][1].content


def test_a_claim_citing_a_segment_that_does_not_exist_is_dropped(model):
    model({"claims": [_claim("Inventata.", 9, "x")]})
    result = extract_claims(SEGMENTS, source_name="procedura.md")
    assert result.claims == []
    assert result.discarded == 1


def test_a_quote_not_found_in_its_segment_is_kept_but_marked_unverified(model):
    model({"claims": [_claim("L'ordine O-2 l'ha approvato il CFO.", 2, "il direttore ha firmato l'ordine")]})
    [claim] = extract_claims(SEGMENTS, source_name="procedura.md").claims
    assert claim.quote_verified is False
    assert claim.anchor_ref == "R4"


def test_the_same_statement_twice_is_kept_once(model):
    duplicate = _claim("Il buyer approva sotto soglia.", 1, "approva il buyer")
    model({"claims": [duplicate, {**duplicate, "statement": "il buyer approva sotto soglia."}]})
    assert len(extract_claims(SEGMENTS, source_name="procedura.md").claims) == 1


def test_no_text_no_call(model):
    model(forbid=True)
    result = extract_claims([{"ordinal": 0, "ref": "§1", "text": "   "}], source_name="vuoto.md")
    assert result.claims == []


def test_a_long_document_says_how_many_segments_were_left_out():
    long_segments = [
        {"ordinal": index, "ref": f"§{index + 1}", "text": "x" * 1_000} for index in range(MAX_INPUT_CHARS // 900)
    ]
    _rendered, shown, left_out = render_segments(long_segments)
    assert left_out > 0
    assert len(shown) + left_out == len(long_segments)
    # Un tratto continuo dall'inizio: niente buchi nel mezzo.
    assert sorted(shown) == list(range(len(shown)))
