"""Le metriche di retrieval dicono il vero, su classifiche scritte a mano."""

from __future__ import annotations

import pytest

from tests.evals.retrieval_metrics import (
    QueryResult,
    aggregate,
    retrieval_regressions,
    score_query,
)

PASSAGES = ["la soglia e' di 5.000 euro", "servono due offerte"]
USEFUL_A = "Sopra la soglia e' di 5.000 euro, dice Laura."
USEFUL_B = "In quel caso servono   due\nofferte allegate."
NOISE = "Il modulo standard e' l'unico canale."


def test_the_useful_chunks_on_top_score_full_marks():
    result = score_query("q", [USEFUL_A, USEFUL_B, NOISE], PASSAGES, k=2, relevant_in_corpus=2)

    assert result.recall_at_k == 1.0
    assert result.precision_at_k == 1.0
    assert result.reciprocal_rank == 1.0
    assert result.ndcg_at_k == 1.0
    assert result.missed_passages == []


def test_a_passage_split_by_spaces_and_line_breaks_is_still_found():
    result = score_query("q", [USEFUL_B], ["servono due offerte"], k=1, relevant_in_corpus=1)

    assert result.recall_at_k == 1.0


def test_useful_chunks_ranked_low_keep_recall_and_lose_order():
    result = score_query("q", [NOISE, USEFUL_A, USEFUL_B], PASSAGES, k=3, relevant_in_corpus=2)

    assert result.recall_at_k == 1.0
    assert result.precision_at_k == pytest.approx(2 / 3, abs=0.001)
    assert result.reciprocal_rank == 0.5
    assert result.ndcg_at_k < 1.0


def test_a_passage_outside_the_top_k_is_missed():
    result = score_query("q", [USEFUL_A, NOISE, USEFUL_B], PASSAGES, k=2, relevant_in_corpus=2)

    assert result.recall_at_k == 0.5
    assert result.missed_passages == ["servono due offerte"]


def test_nothing_useful_scores_zero():
    result = score_query("q", [NOISE], PASSAGES, k=5, relevant_in_corpus=2)

    assert (result.recall_at_k, result.precision_at_k, result.reciprocal_rank, result.ndcg_at_k) == (
        0.0,
        0.0,
        0.0,
        0.0,
    )


def test_the_averages_and_the_regressions_against_a_baseline():
    results = [
        QueryResult("a", recall_at_k=1.0, precision_at_k=0.4, reciprocal_rank=1.0, ndcg_at_k=1.0),
        QueryResult("b", recall_at_k=0.5, precision_at_k=0.2, reciprocal_rank=0.5, ndcg_at_k=0.6),
    ]

    current = aggregate(results)

    assert current == {"recall_at_k": 0.75, "precision_at_k": 0.3, "mrr": 0.75, "ndcg_at_k": 0.8}
    assert retrieval_regressions(current, {**current, "mrr": 0.9}) == ["mrr 0.900 -> 0.750"]
    assert retrieval_regressions(current, {**current, "mrr": 0.76}) == []
