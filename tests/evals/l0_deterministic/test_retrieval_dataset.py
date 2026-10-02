"""Il dataset di retrieval dice il vero sulle sue fonti.

Come per il golden set: un passo atteso ritoccato a memoria non sta in nessun
chunk, e il retrieval verrebbe punito per un refuso di chi ha scritto la domanda.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.evals.retrieval_metrics import RetrievalSet, flat

EVALS = Path(__file__).resolve().parents[1]
GOLDEN = EVALS.parent / "golden"
DATASET = RetrievalSet.load(EVALS / "l1_retrieval" / "queries.json")


@pytest.mark.parametrize("query", DATASET.queries, ids=lambda query: query.id)
def test_every_expected_passage_is_in_its_source_word_for_word(query):
    sources = GOLDEN / query.case / "sources"
    assert sources.is_dir(), f"{query.id}: il caso {query.case} non esiste nel golden set"

    missing = [
        f"«{passage.quote}» non e' in {passage.source}"
        for passage in query.passages
        if flat(passage.quote) not in flat((sources / passage.source).read_text(encoding="utf-8"))
    ]

    assert not missing, "\n".join(missing)


def test_the_dataset_covers_every_golden_case():
    cases = {folder.name for folder in GOLDEN.iterdir() if (folder / "expected.json").exists()}

    assert cases <= {query.case for query in DATASET.queries}
