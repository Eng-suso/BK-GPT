"""B3.1: arrivi non stazionari, misurati sul banco di G3b senza cambiarlo.

    tests/simulation/benchmark/g3b/setup_envs.sh        # venv di ricerca, una volta
    uv run python tests/simulation/benchmark/b3_1/run.py --phases validation [--logs K ...] [--configs C ...]
    uv run python tests/simulation/benchmark/b3_1/report.py

Riusa ``g3b/run.py`` per tutto (fasi, discovery SIMOD in cache, Prosimos della ricerca,
metriche, budget del §6) e aggiunge solo le configurazioni degli arrivi di B3.1, ognuna con
la sua scheda in ``docs/vpt/LOG.md`` scritta prima della misura. Le configurazioni di G3b
girano con il loro codice, invariato; i risultati vanno in ``b3_1/results/`` e la cache in
``/var/tmp/delir-b3_1/work`` (``B3_1_DIR``), cosi' il banco di G3b e chi lo usa in parallelo
non vedono nulla di questo driver.

I log si misurano nell'ordine dato con ``--logs``: con due processi in parallelo si
ordinano in modo che i due log piu' pesanti (BPIC 2017 W, BPIC 2012) non girino insieme.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

if __package__ in (None, ""):  # lanciato come script
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from tests.simulation.benchmark import protocol
from tests.simulation.benchmark.b3_1 import arrivals
from tests.simulation.benchmark.eval_harness import DEFAULT_SEED, PAPER_REPLICAS
from tests.simulation.benchmark.g3b import run as g3b
from tests.simulation.benchmark.run_baseline import replicas_error

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
STATE = Path(os.environ.get("B3_1_DIR", "/var/tmp/delir-b3_1"))

# Le configurazioni di G3b che servono a B3.1: il candidato C1 e le sue due basi.
G3B_CONFIGS = ("naive", "simod_extr", "simod_extr_replay")
CONFIGS = {**{c: g3b.CONFIGS[c] for c in G3B_CONFIGS}, **{name: v.label for name, v in arrivals.VARIANTS.items()}}


def simulate(config: str, prepared: g3b.Prepared, out: Path, seed: int, replicas: int) -> tuple[list, dict]:
    """Le configurazioni di G3b con il loro codice; le varianti di B3.1 nello scenario ``simod_extr``."""
    variant = arrivals.VARIANTS.get(config)
    if variant is None:
        return g3b_simulate(config, prepared, out, seed, replicas)
    folder, meta = g3b.simod_extr(prepared)
    began = time.perf_counter()
    instants = [variant.build(prepared, seed + replica) for replica in range(replicas)]
    built = round(time.perf_counter() - began, 3)
    path = out / "arrivals.json"
    path.write_text(json.dumps([[i.isoformat() for i in replica] for replica in instants]), encoding="utf-8")
    run = g3b.prosimos(folder / "model.bpmn", folder / "scenario.json",
                       g3b.tool_args(prepared.cases, prepared.start, seed, replicas, out), out, replicas, "--arrivals", str(path))
    timings = json.loads((out / "timings.json").read_text(encoding="utf-8"))
    cost = {
        "discovery_seconds": round(meta["seconds"] + built, 3),
        "discovery_peak_mb": meta["peak_mb"],
        "arrivals_seconds": built,
        "simulation_seconds": timings["simulation_seconds"],
        "simulation_peak_mb": run.peak_mb,
        "val01": g3b.val01(folder),
    }
    return [out / f"sim_{r}.csv" for r in range(replicas)], cost


g3b_simulate = g3b.simulate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--logs", nargs="*", help="chiavi dei log di sviluppo, nell'ordine in cui misurarli (default: tutti)")
    parser.add_argument("--configs", nargs="*", default=list(G3B_CONFIGS), choices=list(CONFIGS))
    parser.add_argument("--phases", nargs="*", default=list(g3b.PHASES), choices=g3b.PHASES)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--replicas", type=int, default=PAPER_REPLICAS)
    parser.add_argument("--force", action="store_true", help="rifa' anche le misure gia' scritte")
    parser.add_argument("--retry-failed", action="store_true", help="riprova le configurazioni fallite")
    args = parser.parse_args(argv)
    if error := replicas_error(args.replicas):
        parser.error(error)

    known = {log.key: log for log in protocol.development_logs()}
    if unknown := [key for key in args.logs or [] if key not in known]:
        parser.error(f"log sconosciuti: {', '.join(unknown)}")
    logs = [known[key] for key in args.logs] if args.logs else list(known.values())
    with ExitStack() as stack:
        # Il banco di G3b con la cache di B3.1, le sue configurazioni in piu' e nient'altro.
        stack.enter_context(mock.patch.object(g3b, "WORK", STATE / "work"))
        stack.enter_context(mock.patch.object(g3b, "simulate", simulate))
        stack.enter_context(mock.patch.dict(g3b.CONFIGS, CONFIGS))
        stack.enter_context(protocol.selection_phase())
        for log in logs:
            todo = {
                phase: [c for c in args.configs if args.force or not g3b._done(
                    RESULTS / log.key / phase / f"{c}.json", retry_failed=args.retry_failed, seed=args.seed, replicas=args.replicas)]
                for phase in args.phases
            }
            if not any(todo.values()):
                continue
            loaded = g3b.periods(log)
            for phase in args.phases:
                if not todo[phase]:
                    continue
                prepared = g3b.prepare(log, phase, loaded)
                for config in todo[phase]:
                    began = time.time()
                    result = g3b.evaluate(config, prepared, seed=args.seed, replicas=args.replicas)
                    result["b3_1"] = "tests/simulation/benchmark/b3_1/run.py"
                    target = RESULTS / log.key / phase / f"{config}.json"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                    print(f"{log.key} {phase} {config}: {result['status']} ({time.time() - began:.0f} s)"
                          + (f" {result.get('reason', '')[:300]}" if result["status"] != "measured" else ""), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
