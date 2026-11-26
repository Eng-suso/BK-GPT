"""G3: le due trasformazioni deterministiche dello spike (gemello ingenuo, diagnosi dei cicli)."""

from __future__ import annotations

import json
import shutil

import pytest

from tests.simulation.benchmark.g3 import evaluate, fix_dead_loops


def test_the_naive_twin_is_seeded_and_has_an_interval():
    first = evaluate.naive_metrics("AcademicCredentials", seed=20261124, replicas=3)
    again = evaluate.naive_metrics("AcademicCredentials", seed=20261124, replicas=3)

    assert first == again
    assert all(first[m]["ci95"] > 0 for m in ("cycle_time_w1", "relative_event", "case_arrival"))


def test_the_dead_loop_of_academic_credentials_is_reopened_at_the_train_frequency(tmp_path):
    source = fix_dead_loops.HERE / "discovered" / "AcademicCredentials_diff"
    folder = tmp_path / source.name
    shutil.copytree(source, folder)

    changes = fix_dead_loops.fix(folder)

    assert changes == [{
        "gateway": "node_59fc62b1-3b4e-4c11-ba7b-1cab3392cdaa",
        "after": "Avanzar recepcion documentos",
        "exit_probability": 2 / 3,
        "train_cases": 2,
        "train_executions": 3,
    }]
    fixed = json.loads((tmp_path / "AcademicCredentials_diff-loopfix" / "AcademicCredentials.json").read_text())
    gateway = next(g for g in fixed["gateway_branching_probabilities"] if g["gateway_id"] == changes[0]["gateway"])
    assert sorted(p["value"] for p in gateway["probabilities"]) == pytest.approx([1 / 3, 2 / 3])


def test_a_scenario_without_dead_loops_is_left_alone(tmp_path):
    source = fix_dead_loops.HERE / "discovered" / "BPIC_2012_W_diff"
    folder = tmp_path / source.name
    shutil.copytree(source, folder)

    assert fix_dead_loops.fix(folder) == []
    assert not (tmp_path / "BPIC_2012_W_diff-loopfix").exists()
