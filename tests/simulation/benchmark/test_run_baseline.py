"""SIM-36: il gemello ingenuo "B = A" misurato con le distanze di B2, senza rete."""

import gzip
import json
import random
from datetime import UTC, datetime, timedelta

import pytest

from tests.simulation.benchmark import run_baseline
from tests.simulation.benchmark.benchmark_datasets import DatasetUnavailable
from tests.simulation.benchmark.log_distance import METRICS, Event, distances
from tests.simulation.benchmark.run_baseline import naive_replica, run, split_in_half

MONDAY_9 = datetime(2026, 1, 5, 9, tzinfo=UTC)


def _case(case_id: str, start: datetime, hours: float) -> list[Event]:
    middle = start + timedelta(hours=hours / 2)
    return [Event(case_id, "Ricevi", start, middle), Event(case_id, "Approva", middle, start + timedelta(hours=hours))]


def test_the_log_splits_in_half_by_case_start():
    events = [e for i in range(4) for e in _case(str(i), MONDAY_9 + timedelta(days=i), 1)]

    period_a, period_b, cutoff = split_in_half(events)

    assert {e.case_id for e in period_a} == {"0", "1"}
    assert {e.case_id for e in period_b} == {"2", "3"}
    assert cutoff == MONDAY_9 + timedelta(days=2)


def test_one_case_cannot_be_split():
    with pytest.raises(ValueError, match="due casi"):
        split_in_half(_case("solo", MONDAY_9, 1))


def test_the_naive_twin_keeps_the_calendar_of_a():
    period_a = _case("a", MONDAY_9, 2)
    # B parte 10 giorni e 5 ore dopo: A si sposta di settimane intere, non di 10 giorni e 5 ore.
    period_b = _case("b1", MONDAY_9 + timedelta(days=10, hours=5), 2) + _case("b2", MONDAY_9 + timedelta(days=11), 2)

    replica = naive_replica(period_a, period_b, random.Random(1))

    assert {e.case_id for e in replica} == {"a#0", "a#1"}
    first = min(e.start for e in replica)
    assert first - MONDAY_9 == timedelta(weeks=1)
    assert (first.weekday(), first.hour) == (MONDAY_9.weekday(), MONDAY_9.hour)


def test_b_equal_to_a_scores_zero_and_slower_b_scores_what_b2_measures():
    period_a = _case("a", MONDAY_9, 2)
    same = _case("b", MONDAY_9 + timedelta(weeks=3), 2)
    slower = _case("b", MONDAY_9 + timedelta(weeks=3), 4)

    assert distances(same, naive_replica(period_a, same, random.Random(1))) == dict.fromkeys(METRICS, 0.0)
    measured = distances(slower, naive_replica(period_a, slower, random.Random(1)))
    # Le stesse distanze di B2, in ore: il caso di B dura 2 ore di piu'.
    assert measured["cycle_time_w1"] == pytest.approx(2.0)
    assert measured["ngram"] == 0.0


def _xes(cases: int) -> bytes:
    trace = """  <trace><string key="concept:name" value="{case}"/>
    <event><string key="concept:name" value="Ricevi"/><string key="lifecycle:transition" value="START"/><string key="org:resource" value="anna"/><date key="time:timestamp" value="2011-10-{day:02d}T09:00:00+02:00"/></event>
    <event><string key="concept:name" value="Ricevi"/><string key="lifecycle:transition" value="COMPLETE"/><string key="org:resource" value="anna"/><date key="time:timestamp" value="2011-10-{day:02d}T{hour:02d}:00:00+02:00"/></event>
  </trace>"""
    body = "\n".join(trace.format(case=i, day=i + 1, hour=10 + i % 3) for i in range(cases))
    return gzip.compress(f'<?xml version="1.0" encoding="UTF-8"?>\n<log xmlns="http://www.xes-standard.org/">\n{body}\n</log>'.encode())


@pytest.fixture
def logs(tmp_path, monkeypatch):
    """``fetch`` restituisce un XES locale; ``unavailable`` simula 4TU in manutenzione."""
    path = tmp_path / "log.xes.gz"
    path.write_bytes(_xes(12))
    down: set[str] = set()

    def fake_fetch(dataset):
        if dataset.key in down:
            raise DatasetUnavailable(f"{dataset.key}: HTTP Error 503: StorageMaintenance")
        return path

    monkeypatch.setattr(run_baseline, "fetch", fake_fetch)
    return down


def test_each_log_is_saved_with_b2_metrics_and_intervals(tmp_path, logs):
    out = tmp_path / "sim36"

    assert run(["bpic2012"], out, replicas=3) == 0

    report = json.loads((out / "bpic2012.json").read_text())
    assert report["status"] == "measured"
    assert report["distances"].startswith("come B2")
    assert report["cases"] == {"A": 6, "B": 6}
    assert report["seeds"] == [run_baseline.DEFAULT_SEED + r for r in range(3)]
    assert set(report["metrics"]) == set(METRICS)
    for summary in report["metrics"].values():
        assert set(summary) == {"mean", "ci95", "replicas"} and len(summary["replicas"]) == 3
    assert "| bpic2012 |" in (out / "baseline.md").read_text()


def test_same_seed_same_file_bit_for_bit(tmp_path, logs):
    run(["bpic2012"], tmp_path / "one", replicas=3)
    run(["bpic2012"], tmp_path / "two", replicas=3)
    run(["bpic2012"], tmp_path / "other", replicas=3, seed=7)

    first = (tmp_path / "one" / "bpic2012.json").read_bytes()
    assert first == (tmp_path / "two" / "bpic2012.json").read_bytes()
    assert first != (tmp_path / "other" / "bpic2012.json").read_bytes()


def test_a_missing_log_says_why_and_keeps_the_other(tmp_path, logs):
    out = tmp_path / "sim36"
    run(["bpic2012"], out, replicas=3)
    logs.add("bpic2013_incidents")

    assert run(["bpic2013_incidents"], out, replicas=3) == 1

    missing = json.loads((out / "bpic2013_incidents.json").read_text())
    assert missing["status"] == "unavailable" and "503" in missing["reason"]
    table = (out / "baseline.md").read_text()
    assert "| bpic2012 |" in table
    assert "bpic2013_incidents: non misurato" in table and "503" in table


def test_replicas_without_an_interval_are_refused():
    with pytest.raises(SystemExit):
        run_baseline.main(["--replicas", "1"])
