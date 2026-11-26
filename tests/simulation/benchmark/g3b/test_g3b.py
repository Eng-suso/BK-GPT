"""G3b: la logica del driver e dei verdetti, senza strumenti esterni ne' rete.

    uv run pytest --noconftest -q tests/simulation/benchmark/g3b/test_g3b.py
"""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tests.simulation.benchmark import protocol
from tests.simulation.benchmark.g3b import report, run
from tests.simulation.benchmark.log_distance import METRICS


def _result(means: dict[str, float], *, ci: float = 0.1, status: str = "measured", nv: tuple[str, ...] = (), **cost) -> dict:
    return {
        "status": status,
        "label": "x",
        "identifiability": {m: protocol.NOT_VALIDATED if m in nv else protocol.IDENTIFIABLE for m in METRICS},
        "metrics": {m: {"mean": means.get(m, 1.0), "ci95": ci} for m in METRICS},
        "cost": {"discovery_seconds": 10.0, "simulation_seconds": [1.0], "peak_mb": 100.0, **cost},
    }


def test_compare_needs_separated_intervals() -> None:
    low, high = _result({"ngram": 0.1}), _result({"ngram": 0.5})
    assert report.compare(low, high, "ngram") == "vince"
    assert report.compare(high, low, "ngram") == "perde"
    assert report.compare(_result({"ngram": 0.15}), low, "ngram") == "pari"


def test_a_missing_candidate_loses_and_a_missing_base_is_incomplete() -> None:
    measured = _result({})
    assert report.compare(None, measured, "ngram") == "perde"
    assert report.compare(_result({}, status="out_of_budget"), measured, "ngram") == "perde"
    assert report.compare(measured, None, "ngram") == "incompleto"


def test_a_failed_base_loses_and_two_failures_tie() -> None:
    failed = _result({}, status="failed")
    assert report.compare(_result({}), failed, "ngram") == "vince"
    assert report.compare(_result({}, status="not_applicable"), failed, "ngram") == "pari"


CARD = report.Card("prova", "cand", ("naive", "base"), "ngram", "per costruzione")


def _results(candidate: dict[str, dict], base: dict[str, dict]) -> dict:
    out = {}
    for log in candidate:
        out[(log, "test", "cand")] = candidate[log]
        out[(log, "test", "base")] = base[log]
        out[(log, "test", "naive")] = _result({"ngram": 9.0})
    return out


def test_go_when_the_primary_wins_on_the_majority_and_never_loses() -> None:
    good, bad = _result({"ngram": 0.1}), _result({"ngram": 0.5})
    results = _results({"a": good, "b": good, "c": _result({"ngram": 0.45})}, {"a": bad, "b": bad, "c": bad})
    assert report.verdict(CARD, "test", results, ["a", "b", "c"])["verdict"] == "GO"


def test_no_go_when_the_primary_loses_once() -> None:
    good, bad = _result({"ngram": 0.1}), _result({"ngram": 0.5})
    results = _results({"a": good, "b": good, "c": bad}, {"a": bad, "b": bad, "c": good})
    v = report.verdict(CARD, "test", results, ["a", "b", "c"])
    assert v["verdict"] == "NO-GO" and any("perde su c" in r for r in v["reasons"])


def test_no_go_when_a_guard_loses_on_two_logs() -> None:
    cand = _result({"ngram": 0.1, "case_arrival": 5.0})
    base = _result({"ngram": 0.5, "case_arrival": 1.0})
    results = _results({"a": cand, "b": cand}, {"a": base, "b": base})
    v = report.verdict(CARD, "test", results, ["a", "b"])
    assert v["verdict"] == "NO-GO" and any("guardia CAR" in r for r in v["reasons"])


def test_no_go_when_twice_as_expensive_as_a_model_base_but_not_against_b_equals_a() -> None:
    cand = _result({"ngram": 0.1}, discovery_seconds=100.0)
    base = _result({"ngram": 0.5}, discovery_seconds=10.0)
    results = _results({"a": cand, "b": cand}, {"a": base, "b": base})
    v = report.verdict(CARD, "test", results, ["a", "b"])
    assert v["bases"]["naive"]["costlier_than_double"] == []
    assert v["bases"]["base"]["costlier_than_double"] == ["a", "b"] and v["verdict"] == "NO-GO"


def test_the_cost_rule_ignores_a_base_that_was_stopped() -> None:
    cand = _result({"ngram": 0.1}, discovery_seconds=100.0)
    stopped = _result({"ngram": 0.5}, status="out_of_budget", discovery_seconds=10.0)
    results = _results({"a": cand, "b": cand}, {"a": stopped, "b": stopped})
    assert report.verdict(CARD, "test", results, ["a", "b"])["bases"]["base"]["costlier_than_double"] == []


def test_a_result_with_other_seed_or_replicas_is_redone(tmp_path: Path) -> None:
    path = tmp_path / "x.json"
    path.write_text(json.dumps({"status": "failed", "seed": 1, "replicas": 10}))
    assert run._done(path, retry_failed=False, seed=1, replicas=10)
    assert not run._done(path, retry_failed=True, seed=1, replicas=10)
    assert not run._done(path, retry_failed=False, seed=1, replicas=3)


def test_not_validated_when_the_primary_is_identifiable_in_fewer_than_two_logs() -> None:
    nv = _result({"ngram": 0.1}, nv=("ngram",))
    results = _results({"a": nv, "b": nv, "c": _result({"ngram": 0.1})}, {k: _result({"ngram": 0.5}) for k in "abc"})
    assert report.verdict(CARD, "test", results, ["a", "b", "c"])["verdict"] == "NOT VALIDATED"


def test_agentsimulator_cannot_pass_val01() -> None:
    card = report.Card("prova", "cand", ("naive", "base"), "ngram", "non verificabile")
    good, bad = _result({"ngram": 0.1}), _result({"ngram": 0.5})
    v = report.verdict(card, "test", _results({"a": good, "b": good}, {"a": bad, "b": bad}), ["a", "b"])
    assert v["verdict"] == "NO-GO" and any("VAL-01" in r for r in v["reasons"])


def test_the_discovery_input_keeps_missing_starts_empty_and_integer_ids(tmp_path: Path, monkeypatch) -> None:
    t = datetime(2024, 1, 1, 9, tzinfo=UTC)
    rows = [run.Row("c-b", "A", "r1", None, t), run.Row("c-a", "B", "", t, t + timedelta(hours=1))]
    log = protocol.development_logs()[0]
    prepared = run.Prepared(log, "test", rows, [], run.ZoneInfo("UTC"), tmp_path, {})
    run._write_input(prepared)
    with open(prepared.input_csv, newline="") as handle:
        written = list(csv.DictReader(handle))
    assert [w["case_id"] for w in written] == ["0", "1"]
    assert written[1]["start_time"] == "" and written[0]["resource"] == "missing"


@pytest.mark.parametrize(
    "header, row",
    [
        ("case_id,activity,enable_time,start_time,end_time,resource", "0,A,2024-01-01 09:00:00+00:00,2024-01-01 09:00:00+00:00,2024-01-01 10:00:00+00:00,r"),
        ("case_id,activity_name,start_timestamp,end_timestamp,agent,resource", "0,A,2024-01-01 09:00:00+00:00,2024-01-01 10:00:00+00:00,1,r"),
    ],
)
def test_simulated_logs_of_every_tool_are_read(tmp_path: Path, header: str, row: str) -> None:
    path = tmp_path / "sim.csv"
    path.write_text(f"{header}\n{row}\n0,zzz_end,2024-01-01 10:00:00+00:00,2024-01-01 10:00:00+00:00,1,r\n" if "agent" in header else f"{header}\n{row}\n")
    events = run.read_simulated(path)
    assert len(events) == 1 and events[0].end - events[0].start == timedelta(hours=1)


def test_the_cards_cover_every_configuration_the_plan_names() -> None:
    named = {c.candidate for c in report.CARDS} | {b for c in report.CARDS for b in c.bases}
    assert {"naive", "simod", "simod_extr", "simod_extr_atkde", "prosit", "agentsim"} <= named <= set(run.CONFIGS)
    assert json.dumps(run.CONFIGS)  # etichette serializzabili nei risultati
