"""G3b: AgentSimulator (Kirchdorfer et al., 2024) scopre e simula.

Gira nel venv di ricerca di AgentSimulator, dalla cartella del repository (``cwd``),
e non importa nulla di DeliR:

    python agentsim_run.py --input IN.csv --cases N --start ISO --seed S --replicas R --out DIR

La pipeline e' quella di ``AgentSimulator.execute_pipeline`` con
``determine_automatically`` (architettura e ritardi estranei scelti da lui, il default
del paper): la sua validazione interna e' il 20% finale dei casi dell'input, come nel
suo ``_split_log``. Del periodo da prevedere passa solo cio' che usa (il primo inizio e
il numero dei casi): un log fittizio di N casi che iniziano tutti a ``--start``. Il
caso con ``--train_path`` di ``simulate.py`` non funziona (``df_train_big`` non e'
definito): per questo la pipeline si chiama qui, un passo alla volta.

Seed della replica r: ``S + r`` su ``random`` e ``numpy`` (Mesa usa ``random``).
Scrive ``DIR/sim_<r>.csv`` e ``DIR/timings.json``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import random
import time
import warnings
from pathlib import Path

# Il codice dello strumento sta nella cartella del suo repository, la cwd.
sys.path.insert(0, os.getcwd())

import numpy
import pandas
from source import simulation as agent_simulation
from source.discovery import discover_simulation_parameters

RENAME = {"activity": "activity_name", "start_time": "start_timestamp", "end_time": "end_timestamp"}


def read_input(path: Path) -> pandas.DataFrame:
    frame = pandas.read_csv(path, dtype={"resource": str})
    frame["start_time"] = frame["start_time"].fillna(frame["end_time"])
    frame = frame.rename(columns=RENAME)
    for column in ("start_timestamp", "end_timestamp"):
        frame[column] = pandas.to_datetime(frame[column], utc=True, format="ISO8601")
    return frame


def validation_part(frame: pandas.DataFrame) -> pandas.DataFrame:
    """Come ``get_validation_data`` di AgentSimulator: il 20% finale dei casi (ordinati per id)."""
    ordered = frame.sort_values(by=["case_id", "start_timestamp"])
    last = ordered["case_id"].unique()[-int(ordered["case_id"].nunique() * 0.2):]
    return ordered[ordered["case_id"].isin(last)]


def placeholder_target(frame: pandas.DataFrame, cases: int, start: pandas.Timestamp) -> pandas.DataFrame:
    """N casi fittizi che iniziano a ``start``: AgentSimulator ne legge solo il numero e il primo inizio."""
    first = frame.iloc[0]
    return pandas.DataFrame(
        {
            "case_id": range(cases),
            "activity_name": first["activity_name"],
            "resource": first["resource"],
            "start_timestamp": start,
            "end_timestamp": start,
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--cases", type=int, required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--replicas", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    warnings.filterwarnings("ignore")
    args.out.mkdir(parents=True, exist_ok=True)
    work = args.out / "agentsim"
    work.mkdir(exist_ok=True)

    random.seed(args.seed)
    numpy.random.seed(args.seed)
    began = time.perf_counter()
    train = read_input(args.input)
    validation = validation_part(train)
    target = placeholder_target(train, args.cases, pandas.Timestamp(args.start).tz_convert("UTC"))
    try:
        train, parameters = discover_simulation_parameters(
            train, target, validation, str(work), args.cases, validation["case_id"].nunique(),
            determine_automatically=True, central_orchestration=False, discover_extr_delays=False,
        )
    except ValueError as exc:
        # Un input che dura meno di un giorno: la media degli arrivi per giorno e' NaN.
        if "NaN" in str(exc) and train["start_timestamp"].dt.date.nunique() < 2:
            raise SystemExit(f"AgentSimulator non applicabile: input di un solo giorno ({exc})") from exc
        raise
    discovery = round(time.perf_counter() - began, 3)
    arrivals = list(parameters["case_arrival_times"])

    timings = []
    for replica in range(args.replicas):
        random.seed(args.seed + replica)
        numpy.random.seed(args.seed + replica)
        parameters["case_arrival_times"] = list(arrivals)
        began = time.perf_counter()
        agent_simulation.simulate_process(train, parameters, str(work), 1)
        timings.append(round(time.perf_counter() - began, 3))
        (work / "simulated_log_0.csv").rename(args.out / f"sim_{replica}.csv")
    choice = {k: parameters.get(k) for k in ("central_orchestration", "discover_extr_delays")}
    (args.out / "timings.json").write_text(
        json.dumps({"discovery_seconds": discovery, "simulation_seconds": timings, "choice": choice}, default=str)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
