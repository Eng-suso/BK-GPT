"""B3.2: log sintetici con la verita' delle attese, dai modelli veri di Chapela-Campa e Dumas.

Gira nel venv di ricerca di SIMOD (Prosimos 2.1.0) e non importa nulla di DeliR:

    python truth_logs.py --inputs datasets/extraneous-delays/inputs/synthetic --out DIR --cases 1000 --seed S NOME ...

Per ogni modello (BPMN + JSON del dataset; le varianti ``_after`` usano il JSON di
``_5_timers``, con gli stessi timer) simula ``--cases`` casi dal 2023-01-02 09:00 UTC con
gli eventi nel log (``is_event_added_to_log``): ogni riga ha l'abilitazione vera
(``enable_time``) e ogni timer compare come evento senza risorsa. ``DIR/<nome>.csv``.
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path

import numpy
from prosimos.simulation_engine import run_simulation

START = "2023-01-02T09:00:00.000+00:00"


def scenario_json(inputs: Path, name: str) -> Path:
    if name.endswith("_after"):
        return inputs / (name.removesuffix("_after") + ".json")
    return inputs / f"{name}.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cases", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20261124)
    parser.add_argument("names", nargs="+")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for name in args.names:
        random.seed(args.seed)
        numpy.random.seed(args.seed)
        run_simulation(
            str(args.inputs / f"{name}.bpmn"), str(scenario_json(args.inputs, name)), total_cases=args.cases,
            stat_out_path=None, log_out_path=str(args.out / f"{name}.csv"), starting_at=START, is_event_added_to_log=True,
        )
        print(name, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
