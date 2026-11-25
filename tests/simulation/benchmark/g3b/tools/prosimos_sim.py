"""G3b: simula uno scenario Prosimos (BPMN + JSON di SIMOD) per piu' repliche.

Gira nel venv di ricerca di SIMOD (Prosimos 2.1.0, lo stesso motore del runner del
prodotto) e non importa nulla di DeliR:

    python prosimos_sim.py --bpmn M.bpmn --json S.json --cases N --start ISO \
        --seed S --replicas R --out DIR [--arrivals A.json] [--calendars-247]

- senza ``--arrivals`` gli arrivi li campiona Prosimos dallo scenario, come il runner;
- con ``--arrivals`` (lista di R liste di istanti ISO, una per replica) i casi arrivano
  in quegli istanti: e' la strada di ``run_simulation(..., fixed_arrival_times=...)``,
  ripetuta qui con la scrittura del log come fa il runner (``_simulate_with_arrivals``);
- ``--calendars-247`` sostituisce ogni calendario delle risorse con uno sempre aperto
  (ablazione dei calendari).

Seed della replica r: ``seed + r``, dato a ``random`` e ``numpy`` come il runner.
Scrive ``DIR/sim_<r>.csv`` (il log di Prosimos) e ``DIR/timings.json`` (secondi per replica).
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import signal
import tempfile
import time
from datetime import datetime
from pathlib import Path

import numpy
from prosimos.simulation_engine import SimBPMEnv, execute_full_process, run_simulation
from prosimos.simulation_properties_parser import parse_datetime
from prosimos.simulation_setup import SimDiffSetup

REPLICA_SECONDS = 600  # PROTOCOL.md §6: al massimo 10 minuti per replica


def _over_budget(_signum, _frame):
    raise SystemExit(f"fuori budget: una replica oltre {REPLICA_SECONDS} s")


ALWAYS_OPEN = [{"from": "MONDAY", "to": "SUNDAY", "beginTime": "00:00:00", "endTime": "23:59:59.999999"}]


def open_calendars(scenario: dict) -> dict:
    """Lo stesso scenario con ogni calendario delle risorse aperto sempre (24/7)."""
    scenario = json.loads(json.dumps(scenario))
    for calendar in scenario.get("resource_calendars", []):
        calendar["time_periods"] = ALWAYS_OPEN
        # FUZZY: la disponibilita' sta nelle fasce con probabilita'; qui vale 1 sempre.
        calendar.pop("workload_ratio", None)
    return scenario


def simulate_fixed(bpmn: Path, scenario: Path, start: datetime, arrivals: list[datetime], log_path: Path) -> None:
    setup = SimDiffSetup(str(bpmn), str(scenario), False, len(arrivals))
    setup.start_datetime = start
    offsets = [(a - start).total_seconds() for a in arrivals]
    writer = {"delimiter": ",", "quotechar": '"', "quoting": csv.QUOTE_MINIMAL}
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=True) as stats, open(
        log_path, "w", newline="", encoding="utf-8"
    ) as logs:
        env = SimBPMEnv(setup, csv.writer(stats, **writer), csv.writer(logs, **writer))
        execute_full_process(env, offsets)
        env.log_writer.force_write()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bpmn", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--cases", type=int, required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--replicas", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--arrivals", type=Path)
    parser.add_argument("--calendars-247", action="store_true")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    scenario_path = args.json
    if args.calendars_247:
        scenario_path = args.out / "scenario_247.json"
        scenario_path.write_text(json.dumps(open_calendars(json.loads(args.json.read_text()))))
    arrivals = json.loads(args.arrivals.read_text()) if args.arrivals else None
    start = parse_datetime(args.start, True)
    timings = []
    for replica in range(args.replicas):
        seed = args.seed + replica
        random.seed(seed)
        numpy.random.seed(seed)
        log_path = args.out / f"sim_{replica}.csv"
        signal.signal(signal.SIGALRM, _over_budget)
        signal.alarm(REPLICA_SECONDS)
        began = time.perf_counter()
        if arrivals is None:
            with tempfile.NamedTemporaryFile(suffix=".csv") as stats:
                run_simulation(
                    str(args.bpmn), str(scenario_path), total_cases=args.cases, stat_out_path=stats.name,
                    log_out_path=str(log_path), starting_at=args.start, is_event_added_to_log=False,
                )
        else:
            instants = sorted(datetime.fromisoformat(a) for a in arrivals[replica])
            simulate_fixed(args.bpmn, scenario_path, start, instants, log_path)
        timings.append(round(time.perf_counter() - began, 3))
        signal.alarm(0)
    (args.out / "timings.json").write_text(json.dumps({"simulation_seconds": timings}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
