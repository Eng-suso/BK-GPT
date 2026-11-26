"""G3b: istanti di arrivo dei casi generati da AT-KDE (Kirchdorfer, Oezdemir et al., BPM 2025).

Gira nel venv di ricerca di AT-KDE, dalla cartella del repository (``cwd``), e non
importa nulla di DeliR:

    python atkde_arrivals.py --input IN.csv --cases N --start ISO --seed S --replicas R --out A.json

Il modello si addestra sugli inizi dei casi di ``IN.csv`` (solo l'input della discovery).
Per ogni replica (seed ``S + r``) genera arrivi da ``--start`` in avanti finche' ne ha
almeno N e tiene i primi N: come le altre configurazioni, conosce del periodo da
prevedere solo l'inizio e il numero dei casi. La finestra parte da N diviso il ritmo
medio dell'input, piu' un margine, e raddoppia finche' non bastano.

Si importa solo ``KDEIATGenerator``: ``IAT_Generator`` porterebbe con se' Prophet,
TensorFlow e Chronos, che AT-KDE non usa.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import signal
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import NoReturn

# Il codice dello strumento sta nella cartella del suo repository, la cwd.
sys.path.insert(0, os.getcwd())

import numpy
import pandas
from source.iat_approaches.kde import KDEIATGenerator

MAX_DOUBLINGS = 6
# ``tune_sensitivity`` confronta due finestre di 7 giorni con arrivi: con meno giorni
# AT-KDE si ferma dentro numpy (percentile di una lista vuota). Lo si dice prima.
MIN_DAYS = 14


# Esito per il driver (run.py, stessi numeri): non applicabile e fuori budget (PROTOCOL.md §6).
EXIT_NOT_APPLICABLE = 3
EXIT_OUT_OF_BUDGET = 4


def stop(code: int, message: str) -> NoReturn:
    print(message, file=sys.stderr, flush=True)
    raise SystemExit(code)


@contextmanager
def budget(seconds: int, what: str) -> Iterator[None]:
    """Oltre ``seconds`` di tempo reale lo strumento esce con ``EXIT_OUT_OF_BUDGET``."""

    def expired(_signum, _frame):
        stop(EXIT_OUT_OF_BUDGET, f"fuori budget: {what} oltre {seconds} s")

    previous = signal.signal(signal.SIGALRM, expired)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


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


def case_starts(path: Path) -> list[pandas.Timestamp]:
    log = pandas.read_csv(path)
    starts = pandas.to_datetime(log["start_time"].fillna(log["end_time"]), utc=True, format="ISO8601")
    return sorted(starts.groupby(log["case_id"]).min().tolist())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    common_arguments(parser)
    args = parser.parse_args()
    logging.disable(logging.INFO)

    train = case_starts(args.input)
    days = len({t.date() for t in train})
    if days < MIN_DAYS:
        stop(EXIT_NOT_APPLICABLE, f"AT-KDE non applicabile: {days} giorni con arrivi nell'input, ne servono almeno {MIN_DAYS}")
    start = pandas.Timestamp(args.start).tz_convert("UTC")
    rate = len(train) / max((train[-1] - train[0]).total_seconds(), 1.0)
    first_window = pandas.Timedelta(seconds=1.25 * args.cases / rate) + pandas.Timedelta(days=1)
    replicas, timings, windows = [], [], []
    for replica in range(args.replicas):
        seed_replica(args.seed + replica)
        began = time.perf_counter()
        window = first_window
        with budget(args.discovery_seconds, "generazione degli arrivi"):
            for attempt in range(MAX_DOUBLINGS):
                if attempt:
                    window *= 2
                arrivals = sorted(t for t in KDEIATGenerator(train, {}).generate_arrivals(start, start + window) if t >= start)
                if len(arrivals) >= args.cases:
                    break
            else:
                raise SystemExit(f"AT-KDE: {len(arrivals)} arrivi in {window}, ne servono {args.cases}")
        replicas.append([t.isoformat() for t in arrivals[: args.cases]])
        timings.append(round(time.perf_counter() - began, 3))
        windows.append(str(window))
    args.out.write_text(json.dumps(replicas))
    args.out.with_suffix(".timings.json").write_text(json.dumps({"seconds": timings, "windows": windows}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
