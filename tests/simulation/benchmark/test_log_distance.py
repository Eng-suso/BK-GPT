"""B2: le distanze fra log danno gli stessi numeri di ``log-distance-measures`` 2.2.

Il riferimento (``fixtures/log_distance_reference.json``) e' calcolato dalla
libreria stessa con ``log_distance_reference.py``; qui si confronta il port.
Se la cache di ``extraneous-delays-outputs`` c'e', si controlla anche che il
port riproduca la riga ``<log>_original`` del paper dai suoi 10 log simulati.
"""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tests.simulation.benchmark.eval_harness import INPUTS, PAPER_METRICS, PAPER_REPLICAS
from tests.simulation.benchmark.log_distance import (
    _T_975,
    METRICS,
    Event,
    distances,
    mean_confidence_interval,
    read_csv_log,
    wasserstein_1d,
)

HERE = Path(__file__).resolve().parent
REFERENCE = json.loads((HERE / "fixtures" / "log_distance_reference.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("pair", REFERENCE["pairs"], ids=lambda p: p["simulated"].split("/")[-1])
def test_every_distance_matches_the_library(pair):
    got = distances(read_csv_log(INPUTS / pair["original"]), read_csv_log(INPUTS / pair["simulated"]))

    assert set(got) == set(METRICS) == set(pair["distances"])
    for metric, expected in pair["distances"].items():
        assert got[metric] == pytest.approx(expected, rel=1e-9, abs=1e-12), metric


def test_wasserstein_is_the_area_between_the_two_step_cdfs():
    assert wasserstein_1d([0, 1, 3], [5, 6, 8]) == 5.0
    assert wasserstein_1d([0, 0, 1], [0, 1, 1]) == pytest.approx(1 / 3)
    assert wasserstein_1d([2], [2, 2, 2]) == 0.0


def test_the_interval_is_the_t_student_one_of_the_paper():
    # scipy.stats.t.ppf(0.975, 9) * stdev / sqrt(10), come compute_mean_conf_interval del paper.
    mean, half = mean_confidence_interval([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
    assert mean == 5.5
    assert half == pytest.approx(2.262157162798205 * 3.0276503540974917 / 10**0.5, rel=1e-15)
    with pytest.raises(ValueError):
        mean_confidence_interval([1.0])


def test_the_whole_t_table_is_scipy_s():
    assert list(_T_975) == REFERENCE["t_975"]


def test_naive_timestamps_are_utc_and_gzip_is_read(tmp_path):
    path = tmp_path / "log.csv"
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["case_id", "activity", "start_time", "end_time", "resource"])
        writer.writerow(["1", "A", "2024-01-01T10:00:00", "2024-01-01 11:00:00+01:00", "r"])
    [event] = read_csv_log(path)
    assert event == Event("1", "A", datetime(2024, 1, 1, 10, tzinfo=UTC), datetime(2024, 1, 1, 10, tzinfo=UTC))
    assert event.end - event.start == timedelta(0)


OUTPUTS = Path.home() / ".cache" / "delir-datasets" / "extraneous-delays-outputs" / "real-life-evaluation"


@pytest.mark.skipif(not OUTPUTS.exists(), reason="serve `fetch_datasets.py fetch extraneous-delays-outputs`")
@pytest.mark.parametrize("process", ["AcademicCredentials", "BPIC_2012_W"])
def test_the_port_reproduces_the_paper_row_from_its_own_logs(process):
    with PAPER_METRICS.open(newline="") as handle:
        row = next(r for r in csv.DictReader(handle) if r["name"] == f"{process}_original")
    test_log = read_csv_log(INPUTS / "real-life" / f"{process}_test.csv.gz")
    measured = [distances(test_log, read_csv_log(OUTPUTS / process / f"{process}_sim_original_{i}.csv")) for i in range(PAPER_REPLICAS)]

    for metric, column in (("relative_event", "relative"), ("absolute_event", "absolute")):
        mean, half = mean_confidence_interval([m[metric] for m in measured])
        assert mean == pytest.approx(float(row[f"{column}_mean"]), rel=1e-9)
        assert half == pytest.approx(float(row[f"{column}_cnf"]), rel=1e-6)
