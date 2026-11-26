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
import os
import random
import sys
import threading
import time
import warnings
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import NoReturn

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


# Esito per il driver (run.py, stessi numeri): non applicabile e fuori budget (PROTOCOL.md §6).
EXIT_NOT_APPLICABLE = 3
EXIT_OUT_OF_BUDGET = 4


def stop(code: int, message: str) -> NoReturn:
    print(message, file=sys.stderr, flush=True)
    raise SystemExit(code)


@contextmanager
def budget(seconds: int, what: str) -> Iterator[None]:
    """Oltre ``seconds`` di tempo reale lo strumento esce con ``EXIT_OUT_OF_BUDGET``.

    Un timer su un thread, non ``SIGALRM``: il gestore di un segnale gira solo quando il
    thread principale torna al bytecode, e uno strumento che aspetta i suoi worker
    (joblib in ProSiT) non ci torna mai. ``os._exit`` chiude subito; i figli rimasti li
    ferma il driver.
    """

    def expired() -> None:
        print(f"fuori budget: {what} oltre {seconds} s", file=sys.stderr, flush=True)
        os._exit(EXIT_OUT_OF_BUDGET)

    timer = threading.Timer(seconds, expired)
    timer.daemon = True
    timer.start()
    try:
        yield
    finally:
        timer.cancel()


def common_arguments(parser: argparse.ArgumentParser) -> None:
    """Gli argomenti che il driver passa a ogni strumento (``run._tool_args``)."""
    parser.add_argument("--cases", type=int, required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--replicas", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--discovery-seconds", type=int, default=7200)
    parser.add_argument("--replica-seconds", type=int, default=600)


def seed_replica(seed: int) -> None:
    random.seed(seed)
    numpy.random.seed(seed)


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
    common_arguments(parser)
    args = parser.parse_args()
    warnings.filterwarnings("ignore")
    args.out.mkdir(parents=True, exist_ok=True)

    seed_replica(args.seed)
    began = time.perf_counter()
    # Non ripetibile al bit: i parametri del control flow seguono l'ordine in cui Python
    # itera le transizioni della rete di Petri (oggetti, non nomi). Fra due passate le
    # metriche cambiano dentro gli IC (G3b, LOG.md).
    with budget(args.discovery_seconds, "discovery"):
        log = read_log(args.input)
        net, initial, final = pm4py.discover_petri_net_inductive(log)
        params = SimulatorParameters(net, initial, final)
        params.discover_from_eventlog(log, max_depth_tree=args.depth, verbose=False)
    discovery = round(time.perf_counter() - began, 3)

    start = pandas.Timestamp(args.start).tz_convert("UTC")
    timings = []
    for replica in range(args.replicas):
        seed_replica(args.seed + replica)
        began = time.perf_counter()
        with budget(args.replica_seconds, "una replica"):
            simulated = SimulatorEngine(params).apply(n_traces=args.cases, t_start=start)
        timings.append(round(time.perf_counter() - began, 3))
        out = simulated.rename(columns={v: k for k, v in COLUMNS.items()})[list(COLUMNS)]
        out.to_csv(args.out / f"sim_{replica}.csv", index=False)
    (args.out / "timings.json").write_text(json.dumps({"discovery_seconds": discovery, "simulation_seconds": timings}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
