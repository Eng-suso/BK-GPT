"""SIM-36: il gemello ingenuo "B = A" misurato con le distanze di B2, senza rete."""

import gzip
import json
import random
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.simulation.benchmark import run_baseline
from tests.simulation.benchmark.benchmark_datasets import DatasetUnavailable
from tests.simulation.benchmark.log_distance import METRICS, Event, cases, distances
from tests.simulation.benchmark.run_baseline import naive_replica, run, split_in_half

MONDAY_9 = datetime(2026, 1, 5, 9, tzinfo=UTC)
AMSTERDAM = ZoneInfo("Europe/Amsterdam")


def _case(case_id: str, start: datetime, hours: float) -> list[Event]:
    """Due eventi in UTC, come li produce ``to_events``."""
    start = start.astimezone(UTC)
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
    # La mediana di B e' 10 giorni e 5 ore dopo A: A si sposta di una settimana intera.
    period_b = _case("b1", MONDAY_9 + timedelta(days=9), 2) + _case("b2", MONDAY_9 + timedelta(days=10, hours=5), 2)

    replica = naive_replica(period_a, period_b, random.Random(1), UTC)

    assert {e.case_id for e in replica} == {"a#0", "a#1"}
    first = min(e.start for e in replica)
    assert first - MONDAY_9 == timedelta(weeks=1)
    assert (first.weekday(), first.hour) == (MONDAY_9.weekday(), MONDAY_9.hour)


def test_an_old_isolated_case_does_not_move_the_twin():
    # Un caso di A due anni prima degli altri: lo spostamento segue la mediana, non lui.
    period_a = _case("old", MONDAY_9 - timedelta(weeks=104), 1) + _case("a1", MONDAY_9, 1) + _case("a2", MONDAY_9 + timedelta(days=1), 1)
    period_b = [e for i in range(3) for e in _case(f"b{i}", MONDAY_9 + timedelta(weeks=4, days=i), 1)]

    replica = naive_replica(period_a, period_b, random.Random(3), UTC)

    # Mediana di A: a1 (MONDAY_9); di B: 4 settimane e un giorno dopo. Il caso vecchio non conta.
    original = {case: min(e.start for e in group) for case, group in cases(period_a).items()}
    shifts = {start - original[case.split("#")[0]] for case, start in ((e.case_id, e.start) for e in replica if e.activity == "Ricevi")}
    assert shifts == {timedelta(weeks=4)}


def test_the_local_hour_survives_daylight_saving():
    # A in ottobre (ora legale), B a dicembre: le 9 di Amsterdam restano le 9, non le 8.
    nine_in_october = datetime(2011, 10, 3, 9, tzinfo=AMSTERDAM)
    period_a = _case("a", nine_in_october, 1)
    period_b = _case("b", datetime(2011, 12, 12, 9, tzinfo=AMSTERDAM), 1)

    replica = naive_replica(period_a, period_b, random.Random(1), AMSTERDAM)

    start = min(e.start for e in replica).astimezone(AMSTERDAM)
    assert (start.date().isoformat(), start.hour) == ("2011-12-12", 9)


def test_a_case_across_the_clock_change_keeps_its_duration():
    # Il caso inizia sabato 29 ottobre 2011 e finisce dopo il cambio d'ora: dura 24 ore vere.
    saturday = datetime(2011, 10, 29, 12, tzinfo=AMSTERDAM)
    period_a = _case("a", saturday, 24)
    period_b = _case("b", datetime(2011, 12, 10, 12, tzinfo=AMSTERDAM), 24)

    replica = naive_replica(period_a, period_b, random.Random(1), AMSTERDAM)

    assert max(e.end for e in replica) - min(e.start for e in replica) == timedelta(hours=24)


def test_b_equal_to_a_scores_zero_and_slower_b_scores_what_b2_measures():
    period_a = _case("a", MONDAY_9, 2)
    same = _case("b", MONDAY_9 + timedelta(weeks=3), 2)
    slower = _case("b", MONDAY_9 + timedelta(weeks=3), 4)

    assert distances(same, naive_replica(period_a, same, random.Random(1), UTC)) == dict.fromkeys(METRICS, 0.0)
    measured = distances(slower, naive_replica(period_a, slower, random.Random(1), UTC))
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
    assert report["rows_excluded"] == {}
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


def test_4tu_down_does_not_erase_a_saved_measure(tmp_path, logs):
    out = tmp_path / "sim36"
    run(["bpic2012"], out, replicas=3)
    saved = (out / "bpic2012.json").read_bytes()
    logs.add("bpic2012")

    assert run(["bpic2012"], out, replicas=3) == 1

    assert (out / "bpic2012.json").read_bytes() == saved
    assert "| bpic2012 |" in (out / "baseline.md").read_text()


def test_other_json_files_in_the_folder_are_ignored(tmp_path, logs):
    out = tmp_path / "b2"
    out.mkdir()
    (out / "baseline.json").write_text('{"harness": "B2"}')

    assert run(["bpic2012"], out, replicas=3) == 0
    assert "| bpic2012 |" in (out / "baseline.md").read_text()


def test_replicas_without_an_interval_are_refused(tmp_path, logs):
    with pytest.raises(ValueError, match="repliche"):
        run(["bpic2012"], tmp_path / "sim36", replicas=1)
    assert not (tmp_path / "sim36").exists()
    with pytest.raises(SystemExit):
        run_baseline.main(["--replicas", "1"])
