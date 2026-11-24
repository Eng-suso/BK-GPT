"""G3: le due trasformazioni deterministiche dello spike (gemello ingenuo, diagnosi dei cicli)."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime, timedelta

import pytest

from tests.simulation.benchmark.g3 import evaluate, fix_dead_loops
from tests.simulation.benchmark.log_distance import Event


def _event(case: str, start: datetime) -> Event:
    return Event(case, "A", start, start + timedelta(hours=1))


def test_the_naive_twin_moves_by_whole_weeks_and_keeps_the_weekday():
    train = [_event("1", datetime(2026, 1, 5, 9, tzinfo=UTC)), _event("2", datetime(2026, 1, 6, 14, tzinfo=UTC))]
    test = [_event("9", datetime(2026, 3, 4, 11, tzinfo=UTC))]  # 8 settimane e 2 giorni dopo

    twin = evaluate.naive_twin(train, test)

    assert [e.start - t.start for e, t in zip(twin, train, strict=True)] == [timedelta(weeks=8)] * 2
    assert [e.start.weekday() for e in twin] == [e.start.weekday() for e in train]
    assert [e.end - e.start for e in twin] == [timedelta(hours=1)] * 2


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
