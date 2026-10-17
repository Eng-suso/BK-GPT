"""SIM-36: le metriche del benchmark su log costruiti a mano."""

from datetime import UTC, datetime, timedelta

import pytest

from backend.eventlog.model import CanonicalEvent, EventLog
from tests.simulation.benchmark.benchmark_metrics import (
    compare,
    cycle_times,
    daily_throughput,
    default_sla_target,
    median_case_start,
    naive_prediction,
    relative_wasserstein,
    split_by_case_start,
    total_variation,
    variants,
    wasserstein,
    workload_shares,
)

T0 = datetime(2026, 1, 5, 9, tzinfo=UTC)


def _case(case_id: str, day: int, steps: list[tuple[str, str, int, int]]) -> list[CanonicalEvent]:
    """Passi (attivita', risorsa, minuto di inizio, minuto di fine) dall'inizio del giorno ``day``."""
    base = T0 + timedelta(days=day)
    return [
        CanonicalEvent(case_id=case_id, activity=activity, resource=resource,
                       start=base + timedelta(minutes=start), end=base + timedelta(minutes=end))
        for activity, resource, start, end in steps
    ]


def _log(*cases: list[CanonicalEvent], origin="real") -> EventLog:
    return EventLog(origin=origin, events=tuple(e for case in cases for e in case))


SHORT = [("Ricevi", "anna", 0, 10), ("Approva", "bruno", 20, 30)]
LONG = [("Ricevi", "anna", 0, 10), ("Approva", "bruno", 50, 90)]
SKIP = [("Ricevi", "anna", 0, 10)]


def test_wasserstein_is_the_mean_shift_for_shifted_samples():
    assert wasserstein([1, 2, 3], [1, 2, 3]) == 0
    assert wasserstein([1, 2, 3], [11, 12, 13]) == pytest.approx(10)
    assert relative_wasserstein([11, 12, 13], [1, 2, 3]) == pytest.approx(10 / 2)


def test_total_variation_goes_from_zero_to_one():
    assert total_variation({"a": 2, "b": 2}, {"a": 1, "b": 1}) == 0
    assert total_variation({"a": 1}, {"b": 1}) == 1
    assert total_variation({"a": 3, "b": 1}, {"a": 1, "b": 1}) == pytest.approx(0.25)


def test_cycle_waiting_and_variants_of_a_log():
    log = _log(_case("1", 0, SHORT), _case("2", 0, LONG), _case("3", 1, SKIP))

    assert sorted(cycle_times(log)) == [600, 1800, 5400]
    assert variants(log) == {("Ricevi", "Approva"): 2, ("Ricevi",): 1}
    # anna lavora 30 minuti, bruno 10 + 40.
    assert workload_shares(log) == pytest.approx({"anna": 30 / 80, "bruno": 50 / 80})


def test_throughput_counts_completed_cases_per_day():
    log = _log(*[_case(str(i), i // 2, SHORT) for i in range(6)])

    # 6 casi fra il giorno 0 e il giorno 2: 2 giorni di arco.
    assert daily_throughput(log) == pytest.approx(3)


def test_the_log_splits_in_two_periods_by_case_start():
    log = _log(*[_case(str(i), i, SHORT) for i in range(4)])

    cutoff = median_case_start(log)
    period_a, period_b = split_by_case_start(log, cutoff)

    assert {e.case_id for e in period_a.events} == {"0", "1"}
    assert {e.case_id for e in period_b.events} == {"2", "3"}


def test_a_perfect_prediction_scores_zero_everywhere():
    real = _log(_case("1", 0, SHORT), _case("2", 1, LONG))

    metrics = compare(real, real, sla_target_seconds=1800)

    assert metrics.cycle_time_distribution == 0
    assert metrics.waiting_time_distribution == 0
    assert metrics.throughput_error == 0
    assert metrics.path_frequency_distance == 0
    assert metrics.resource_workload_error == 0
    assert metrics.sla_prediction_error_pp == 0


def test_the_naive_twin_misses_a_period_that_got_slower():
    period_a = _log(*[_case(f"a{i}", i, SHORT) for i in range(4)])
    period_b = _log(*[_case(f"b{i}", 10 + i, LONG) for i in range(4)])
    target = default_sla_target(period_a)

    metrics = compare(naive_prediction(period_a), period_b, sla_target_seconds=target)

    # A: 30 minuti per caso, B: 90. Lo scarto e' due terzi della durata reale.
    assert metrics.cycle_time_distribution == pytest.approx(2 / 3)
    assert metrics.path_frequency_distance == 0
    # In A tutti i casi stanno nell'obiettivo, in B nessuno.
    assert metrics.sla_prediction_error_pp == pytest.approx(100)
    assert metrics.throughput_error == pytest.approx(0)
    assert set(metrics.as_dict()) >= {"cycle_time_distribution", "sla_target_seconds"}


def test_empty_logs_are_refused():
    with pytest.raises(ValueError):
        compare(_log(), _log(_case("1", 0, SHORT)), sla_target_seconds=60)
