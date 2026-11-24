"""B2: l'harness di valutazione.

I test unitari non toccano niente. Quello di riproducibilita' fa il percorso
del prodotto sullo stack reale (``scripts/vpt_stack.sh``) e gira solo se il
runner e' indicato con ``DELIR_TEST_PROSIMOS_URL``.
"""

from __future__ import annotations

import os

import pytest

from tests.simulation.benchmark import eval_harness as harness


def test_the_harness_covers_the_19_scenarios_with_their_reference_logs():
    found = harness.scenarios()

    assert len(found) == 19
    assert [s.name for s in found if s.kind == "real-life"] == list(harness.REAL_LIFE)
    assert sum(s.kind == "synthetic" for s in found) == 16
    assert all(s.reference.exists() and s.model.with_suffix(".bpmn").exists() for s in found)
    assert harness.Scenario("BPIC_2012_W", "real-life").reference.name == "BPIC_2012_W_test.csv.gz"


def test_the_paper_reference_is_the_original_row():
    reference = harness.paper_reference()

    assert reference["AcademicCredentials"]["relative_event"] == (77.21073103049814, 0.3504703967019252)
    assert reference["BPIC_2017_W"]["absolute_event"] == (296.03508226575167, 9.530822339626729)
    # Ricavato dai 10 log del paper con la libreria 2.2: 174,662060 ± 0,962148.
    mean, ci = reference["AcademicCredentials"]["cycle_time_w1"]
    assert (round(mean, 6), round(ci, 6)) == (174.66206, 0.962148)


def _result(log: str, mean: float, ci: float) -> dict:
    metric = {"mean": mean, "ci95": ci, "replicas": []}
    return {"scenario": log, "kind": "real-life", "metrics": dict.fromkeys(harness.PAPER_METRICS_COMPARED, metric)}


def test_inside_means_the_gap_is_smaller_than_the_two_intervals():
    paper = harness.paper_reference()["AcademicCredentials"]["relative_event"]
    rows = harness.compare_with_paper([
        _result("AcademicCredentials", paper[0] + paper[1] + 0.09, 0.1),
        {"scenario": "Pharmacy", "kind": "synthetic", "metrics": {}},
    ])

    red = next(r for r in rows if r["metric"] == "relative_event")
    assert len(rows) == 3
    assert red["inside"] and red["allowed"] == pytest.approx(paper[1] + 0.1)

    outside = harness.compare_with_paper([_result("AcademicCredentials", paper[0] + paper[1] + 0.11, 0.1)])
    assert not next(r for r in outside if r["metric"] == "relative_event")["inside"]
    assert "| AcademicCredentials | RED (ore) |" in harness.comparison_table(rows)


@pytest.mark.skipif(not os.environ.get("DELIR_TEST_PROSIMOS_URL"), reason="serve lo stack reale: scripts/vpt_stack.sh")
def test_same_seed_same_baseline_bit_for_bit(tmp_path):
    scenario = [s for s in harness.scenarios() if s.name == "Pharmacy_1_timer"]

    harness.run(scenario, seed=7, replicas=2, out=tmp_path / "a")
    harness.run(scenario, seed=7, replicas=2, out=tmp_path / "b")
    harness.run(scenario, seed=8, replicas=2, out=tmp_path / "c")

    first = (tmp_path / "a" / "baseline.json").read_bytes()
    assert first == (tmp_path / "b" / "baseline.json").read_bytes()
    assert first != (tmp_path / "c" / "baseline.json").read_bytes()
