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
import os
import sys
import logging
import random
import time
from pathlib import Path

# Il codice dello strumento sta nella cartella del suo repository, la cwd.
sys.path.insert(0, os.getcwd())

import numpy
import pandas
from source.iat_approaches.kde import KDEIATGenerator

MAX_DOUBLINGS = 6
# ``tune_sensitivity`` confronta due finestre di 7 giorni con arrivi: con meno giorni
# AT-KDE si ferma dentro numpy (percentile di una lista vuota). Lo si dice prima.
MIN_DAYS = 14


def case_starts(path: Path) -> list[pandas.Timestamp]:
    log = pandas.read_csv(path)
    starts = pandas.to_datetime(log["start_time"].fillna(log["end_time"]), utc=True, format="ISO8601")
    return sorted(starts.groupby(log["case_id"]).min().tolist())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--cases", type=int, required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--replicas", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    logging.disable(logging.INFO)

    train = case_starts(args.input)
    days = len({t.date() for t in train})
    if days < MIN_DAYS:
        raise SystemExit(f"AT-KDE non applicabile: {days} giorni con arrivi nell'input, ne servono almeno {MIN_DAYS}")
    start = pandas.Timestamp(args.start).tz_convert("UTC")
    rate = len(train) / max((train[-1] - train[0]).total_seconds(), 1.0)
    first_window = pandas.Timedelta(seconds=1.25 * args.cases / rate) + pandas.Timedelta(days=1)
    replicas, timings, windows = [], [], []
    for replica in range(args.replicas):
        seed = args.seed + replica
        random.seed(seed)
        numpy.random.seed(seed)
        began = time.perf_counter()
        window = first_window
        for _ in range(MAX_DOUBLINGS):
            arrivals = sorted(t for t in KDEIATGenerator(train, {}).generate_arrivals(start, start + window) if t >= start)
            if len(arrivals) >= args.cases:
                break
            window *= 2
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
