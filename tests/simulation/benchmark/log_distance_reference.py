"""B2: i numeri di ``log-distance-measures`` 2.2 su coppie di log del repo.

Rigenera ``fixtures/log_distance_reference.json``, il riferimento con cui
``test_log_distance.py`` controlla le formule portate in ``log_distance.py``.
La libreria vuole Python 3.11 o 3.12, quindi questo script gira fuori dal
backend, in un venv apposta:

    uv venv -p 3.12 /tmp/ldm && VIRTUAL_ENV=/tmp/ldm uv pip install log-distance-measures==2.2.0
    /tmp/ldm/bin/python -I tests/simulation/benchmark/log_distance_reference.py

Le chiamate sono quelle del paper e di SIMOD: parametri di default della
libreria, cycle time con bin di un'ora, 3-grammi normalizzati.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
from log_distance_measures.absolute_event_distribution import absolute_event_distribution_distance
from log_distance_measures.case_arrival_distribution import case_arrival_distribution_distance
from log_distance_measures.circadian_event_distribution import circadian_event_distribution_distance
from log_distance_measures.config import EventLogIDs
from log_distance_measures.cycle_time_distribution import cycle_time_distribution_distance
from log_distance_measures.n_gram_distribution import n_gram_distribution_distance
from log_distance_measures.relative_event_distribution import relative_event_distribution_distance

HERE = Path(__file__).resolve().parent
INPUTS = HERE.parents[2] / "datasets" / "extraneous-delays" / "inputs"
OUT = HERE / "fixtures" / "log_distance_reference.json"
IDS = EventLogIDs(case="case_id", activity="activity", resource="resource", start_time="start_time", end_time="end_time")

# (log di riferimento, log confrontato), percorsi relativi a ``inputs``.
PAIRS = [
    ("real-life/AcademicCredentials_test.csv.gz", "real-life/AcademicCredentials_train.csv.gz"),
    ("real-life/BPIC_2012_W_test.csv.gz", "real-life/BPIC_2012_W_train.csv.gz"),
    ("real-life/BPIC_2017_W_test.csv.gz", "real-life/BPIC_2017_W_train.csv.gz"),
    ("synthetic/Pharmacy_5_timers.csv.gz", "synthetic/Pharmacy_5_timers_after.csv.gz"),
    ("synthetic/Procure_to_Pay.csv.gz", "synthetic/Procure_to_Pay_3_timers.csv.gz"),
]


def read(path: Path) -> pd.DataFrame:
    """Come ``pix_framework.io.event_log.read_csv_log``: istanti ISO 8601 in UTC."""
    log = pd.read_csv(path)
    for column in (IDS.start_time, IDS.end_time):
        log[column] = pd.to_datetime(log[column], utc=True, format="ISO8601")
    return log


def distances(original: pd.DataFrame, simulated: pd.DataFrame) -> dict[str, float]:
    return {
        "cycle_time_w1": cycle_time_distribution_distance(original, IDS, simulated, IDS, bin_size=pd.Timedelta(hours=1)),
        "ngram": n_gram_distribution_distance(original, IDS, simulated, IDS, n=3),
        "relative_event": relative_event_distribution_distance(original, IDS, simulated, IDS),
        "absolute_event": absolute_event_distribution_distance(original, IDS, simulated, IDS),
        "circadian_event": circadian_event_distribution_distance(original, IDS, simulated, IDS),
        "case_arrival": case_arrival_distribution_distance(original, IDS, simulated, IDS),
    }


def main() -> int:
    from importlib.metadata import version

    pairs = [
        {"original": a, "simulated": b, "distances": distances(read(INPUTS / a), read(INPUTS / b))}
        for a, b in PAIRS
    ]
    report = {"library": f"log-distance-measures {version('log-distance-measures')}", "pairs": pairs}
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"scritto {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
