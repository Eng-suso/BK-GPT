"""G3b: ProSiT (Vinci et al., ``prosit-pm`` 1.0.5) scopre e simula.

Gira nel venv di ricerca di ProSiT e non importa nulla di DeliR:

    python prosit_run.py --input IN.csv --depth D --cases N --start ISO --seed S --replicas R --out DIR

Scoperta come nel README di ProSiT: rete di Petri dell'Inductive Miner di pm4py e
``discover_from_eventlog`` con ``max_depth_tree=D`` (0 = senza regole), il resto ai
default. Poi R repliche da N casi a partire da ``--start``, seed ``S + r`` dato a
``random`` e ``numpy`` prima di ogni replica. Scrive ``DIR/sim_<r>.csv``
(``case_id, activity, resource, start_time, end_time``) e ``DIR/timings.json``.
"""

from __future__ import annotations

import argparse
import json
import random
import signal
import time
import warnings
from pathlib import Path

import numpy
import pandas
import pm4py
from prosit import SimulatorEngine, SimulatorParameters

COLUMNS = {
    "case_id": "case:concept:name",
    "activity": "concept:name",
    "resource": "org:resource",
    "start_time": "start:timestamp",
    "end_time": "time:timestamp",
}


REPLICA_SECONDS = 600  # PROTOCOL.md §6: al massimo 10 minuti per replica


def _over_budget(_signum, _frame):
    raise SystemExit(f"fuori budget: una replica oltre {REPLICA_SECONDS} s")


def read_log(path: Path):
    frame = pandas.read_csv(path, dtype={"case_id": str, "resource": str})
    frame["start_time"] = frame["start_time"].fillna(frame["end_time"])
    for column in ("start_time", "end_time"):
        frame[column] = pandas.to_datetime(frame[column], utc=True, format="ISO8601")
    frame = frame.rename(columns=COLUMNS)[list(COLUMNS.values())].sort_values(["start:timestamp", "time:timestamp"])
    return pm4py.convert_to_event_log(frame)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--depth", type=int, required=True)
    parser.add_argument("--cases", type=int, required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--replicas", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    warnings.filterwarnings("ignore")
    args.out.mkdir(parents=True, exist_ok=True)

    began = time.perf_counter()
    log = read_log(args.input)
    net, initial, final = pm4py.discover_petri_net_inductive(log)
    params = SimulatorParameters(net, initial, final)
    params.discover_from_eventlog(log, max_depth_tree=args.depth, verbose=False)
    discovery = round(time.perf_counter() - began, 3)

    start = pandas.Timestamp(args.start).tz_convert("UTC")
    timings = []
    for replica in range(args.replicas):
        random.seed(args.seed + replica)
        numpy.random.seed(args.seed + replica)
        signal.signal(signal.SIGALRM, _over_budget)
        signal.alarm(REPLICA_SECONDS)
        began = time.perf_counter()
        simulated = SimulatorEngine(params).apply(n_traces=args.cases, t_start=start)
        timings.append(round(time.perf_counter() - began, 3))
        signal.alarm(0)
        out = simulated.rename(columns={v: k for k, v in COLUMNS.items()})[list(COLUMNS)]
        out.to_csv(args.out / f"sim_{replica}.csv", index=False)
    (args.out / "timings.json").write_text(json.dumps({"discovery_seconds": discovery, "simulation_seconds": timings}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
