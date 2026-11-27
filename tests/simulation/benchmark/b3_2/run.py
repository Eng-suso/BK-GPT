"""B3.2: ablazione pulita dei ritardi estranei, sul banco di G3b.

    uv run python tests/simulation/benchmark/b3_2/run.py [--logs K ...] [--configs C ...] [--phases validation test]

Riusa il driver di G3b (``g3b/run.py``: log, fasi, repliche, budget, misura) e aggiunge
configurazioni sue, senza toccare quelle di G3b:

- ``simod``: lo scenario SIMOD senza ritardi (BPMN, risorse, calendari, durate, arrivi),
  la base. La discovery di SIMOD non ha seed: base e candidato si misurano qui sulla
  stessa discovery in cache (``/var/tmp/delir-g3b/work/<log>/<fase>/simod_diff``);
- ``simod_fixed_extr``: lo stesso scenario piu' SOLO i ritardi estranei scoperti sopra di
  esso dalla fase dei ritardi di SIMOD (``tools/simod_delays.py``). L'unica differenza con
  la base sono i timer;
- ``simod_attr_extr``: lo stesso scenario piu' i timer stimati dall'attribuzione delle attese
  (``attribution.py``: la sola quota "ritardo esterno" di ogni attesa), senza ricerca;
- ``simod_extr``: "SIMOD con ritardi estranei" di G3b, invariato (``g3b.simulate``), la base
  del confronto sui reali.

Risultati in ``b3_2/results/<log>/<fase>/<configurazione>.json``, stesso formato di G3b.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

if __package__ in (None, ""):  # lanciato come script
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

import psutil

from tests.simulation.benchmark import protocol
from tests.simulation.benchmark.eval_harness import DEFAULT_SEED, PAPER_REPLICAS
from tests.simulation.benchmark.b3_2.attribution import (
    Execution,
    add_timers,
    attribute,
    extraneous_delays,
    fit_closest,
    fit_duration,
    on_shift_plus,
)
from tests.simulation.benchmark.log_distance import distances
from tests.simulation.benchmark.g3b import run as g3b
from tests.simulation.benchmark.run_baseline import replicas_error

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
TOOLS = HERE / "tools"

CONFIGS = {
    "simod": "SIMOD senza ritardi (scenario fissato, base dell'ablazione)",
    "simod_fixed_extr": "SIMOD senza ritardi + solo i ritardi estranei di SIMOD (risorse e calendari fissati)",
    "simod_attr_extr": "SIMOD senza ritardi + ritardi esterni dell'attribuzione delle attese (B3.2)",
    "simod_attr_idle": "SIMOD senza ritardi + ritardi esterni con la risorsa libera e in orario (B3.2 v2)",
    "simod_attr_shift": "SIMOD senza ritardi + ritardi esterni senza il fuori orario della risorsa (B3.2 v3)",
    "simod_attr_closest": "come v3, distribuzione piu' vicina al campione (B3.2 v4)",
    "simod_attr_calibrated": "come v3 piu' beta volte il fuori orario, beta scelto sull'input della discovery (B3.2 v5)",
    "simod_extr": g3b.CONFIGS["simod_extr"],
}


# configurazione -> (quota del ritardo, scelta della distribuzione): v1, v2, v3, v4.
ATTRIBUTED = {"simod_attr_extr": ("extraneous", fit_duration), "simod_attr_idle": ("idle", fit_duration),
              "simod_attr_shift": ("on_shift", fit_duration), "simod_attr_closest": ("on_shift", fit_closest)}


def attributed_delays(prepared: g3b.Prepared, config: str) -> tuple[Path, dict]:
    """Lo scenario senza ritardi con i timer dell'attribuzione; costo = discovery senza ritardi + attribuzione."""
    diff_folder, diff = g3b.simod_diff(prepared)

    def build(folder: Path) -> dict:
        began = time.perf_counter()
        executions = [Execution(r.case_id, r.activity, (r.start or r.end).timestamp(), r.end.timestamp(), r.resource or "missing")
                      for r in prepared.source]
        measure, fit = ATTRIBUTED[config]
        delays = extraneous_delays(executions, attribute(executions), measure=measure, fit=fit)
        bpmn, events = add_timers((diff_folder / "model.bpmn").read_text(encoding="utf-8"), delays)
        scenario = json.loads((diff_folder / "scenario.json").read_text(encoding="utf-8"))
        scenario["event_distribution"] = events
        (folder / "model.bpmn").write_text(bpmn, encoding="utf-8")
        (folder / "scenario.json").write_text(json.dumps(scenario), encoding="utf-8")
        (folder / "delays.json").write_text(json.dumps({e["activity"]: e["distribution_params"][0]["value"] for e in events}, indent=2),
                                            encoding="utf-8")
        # Gira nel processo del driver: il picco e' la memoria residente del driver a fine calcolo.
        return {"seconds": round(time.perf_counter() - began, 1), "peak_mb": round(psutil.Process().memory_info().rss / 2**20, 1)}

    folder, attr = g3b._cached(prepared, config, build)
    return folder, {"seconds": diff["seconds"] + attr["seconds"], "peak_mb": diff["peak_mb"], "delays_seconds": attr["seconds"]}


BETAS = (0.0, 0.25, 0.5, 0.75, 1.0)
CALIBRATION_REPLICAS = 3
CALIBRATION_METRICS = ("cycle_time_w1", "relative_event", "absolute_event")


def _scenario_with(diff_folder: Path, delays: dict[str, dict], folder: Path) -> list[dict]:
    """Scrive in ``folder`` il BPMN e lo scenario senza ritardi con i timer di ``delays``."""
    bpmn, events = add_timers((diff_folder / "model.bpmn").read_text(encoding="utf-8"), delays)
    scenario = json.loads((diff_folder / "scenario.json").read_text(encoding="utf-8"))
    scenario["event_distribution"] = events
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "model.bpmn").write_text(bpmn, encoding="utf-8")
    (folder / "scenario.json").write_text(json.dumps(scenario), encoding="utf-8")
    return events


def calibrated_delays(prepared: g3b.Prepared, seed: int) -> tuple[Path, dict]:
    """v5: beta scelto simulando l'ultimo 20% dell'input della discovery (mai la validazione ne' il test).

    Per ogni beta lo scenario con i timer simula i casi della coda dell'input (``protocol.train_validation``
    sull'input) dal loro primo inizio, ``CALIBRATION_REPLICAS`` repliche; vince la somma piu' bassa di
    W1, RED e AED, ognuna divisa per il suo valore con beta = 0. Come la fase dei ritardi di SIMOD,
    lo scenario e' scoperto sull'input intero.
    """
    diff_folder, diff = g3b.simod_diff(prepared)

    def build(folder: Path) -> dict:
        began = time.perf_counter()
        executions = [Execution(r.case_id, r.activity, (r.start or r.end).timestamp(), r.end.timestamp(), r.resource or "missing")
                      for r in prepared.source]
        waitings = attribute(executions)
        _, holdout = protocol.train_validation(prepared.source_events)
        cases, start = len({e.case_id for e in holdout}), min(e.start for e in holdout)
        scores, peak = {}, 0.0
        for beta in BETAS:
            trial = folder / f"beta_{beta}"
            _scenario_with(diff_folder, extraneous_delays(executions, waitings, measure=on_shift_plus(beta)), trial)
            run = g3b.prosimos(trial / "model.bpmn", trial / "scenario.json",
                               g3b.tool_args(cases, start, seed, CALIBRATION_REPLICAS, trial), trial, CALIBRATION_REPLICAS)
            peak = max(peak, run.peak_mb)
            measured_ = [distances(holdout, g3b.read_simulated(trial / f"sim_{r}.csv")) for r in range(CALIBRATION_REPLICAS)]
            scores[beta] = {m: sum(d[m] for d in measured_) / len(measured_) for m in CALIBRATION_METRICS}
        zero = scores[0.0]
        total = {b: sum(v[m] / zero[m] if zero[m] else v[m] for m in CALIBRATION_METRICS) for b, v in scores.items()}
        beta = min(BETAS, key=lambda b: (total[b], b))
        events = _scenario_with(diff_folder, extraneous_delays(executions, waitings, measure=on_shift_plus(beta)), folder)
        for b in BETAS:
            shutil.rmtree(folder / f"beta_{b}", ignore_errors=True)
        (folder / "delays.json").write_text(json.dumps({e["activity"]: e["distribution_params"][0]["value"] for e in events}, indent=2),
                                            encoding="utf-8")
        (folder / "calibration.json").write_text(json.dumps({"beta": beta, "scores": scores, "total": total}, indent=2), encoding="utf-8")
        return {"seconds": round(time.perf_counter() - began, 1),
                "peak_mb": max(peak, round(psutil.Process().memory_info().rss / 2**20, 1)), "beta": beta}

    folder, attr = g3b._cached(prepared, f"simod_attr_calibrated_{seed}", build)
    return folder, {"seconds": diff["seconds"] + attr["seconds"], "peak_mb": max(diff["peak_mb"], attr["peak_mb"]),
                    "delays_seconds": attr["seconds"], "beta": attr["beta"]}


def fixed_delays(prepared: g3b.Prepared, seed: int) -> tuple[Path, dict]:
    """Lo scenario senza ritardi con i soli ritardi di SIMOD; costo = discovery senza ritardi + ritardi."""
    diff_folder, diff = g3b.simod_diff(prepared)

    def build(folder: Path) -> dict:
        template = (g3b.HERE / "configs" / "simod_extr.yml").read_text(encoding="utf-8")
        config = folder / "config.yml"
        config.write_text(template.replace("{train}", str(prepared.input_csv)).replace("{model}", str(diff_folder / "model.bpmn")),
                          encoding="utf-8")
        log_path = folder / "delays.log"
        run = g3b._checked(
            "ritardi di SIMOD",
            g3b.measured([g3b._python("simod"), str(TOOLS / "simod_delays.py"), "--config", str(config),
                          "--bpmn", str(diff_folder / "model.bpmn"), "--json", str(diff_folder / "scenario.json"),
                          "--out", str(folder), "--seed", str(seed), "--discovery-seconds", str(g3b.DISCOVERY_SECONDS)],
                         cwd=folder, log_path=log_path, timeout=g3b.DISCOVERY_SECONDS),
            log_path,
        )
        return {"seconds": run.seconds, "peak_mb": run.peak_mb}

    folder, delays = g3b._cached(prepared, f"simod_fixed_extr_{seed}", build)
    return folder, {"seconds": diff["seconds"] + delays["seconds"], "peak_mb": max(diff["peak_mb"], delays["peak_mb"]),
                    "delays_seconds": delays["seconds"]}


def simulate(config: str, prepared: g3b.Prepared, out: Path, seed: int, replicas: int) -> tuple[list, dict]:
    if config == "simod_extr":
        return g3b.simulate(config, prepared, out, seed, replicas)
    if config == "simod":
        folder, meta = g3b.simod_diff(prepared)
        cost = {"discovery_seconds": meta["seconds"], "discovery_peak_mb": meta["peak_mb"]}
    elif config == "simod_attr_calibrated":
        folder, meta = calibrated_delays(prepared, seed)
        cost = {"discovery_seconds": meta["seconds"], "discovery_peak_mb": meta["peak_mb"], "delays_seconds": meta["delays_seconds"],
                "beta": meta["beta"], "delays": json.loads((folder / "delays.json").read_text(encoding="utf-8"))}
    elif config == "simod_fixed_extr" or config in ATTRIBUTED:
        folder, meta = fixed_delays(prepared, seed) if config == "simod_fixed_extr" else attributed_delays(prepared, config)
        cost = {"discovery_seconds": meta["seconds"], "discovery_peak_mb": meta["peak_mb"], "delays_seconds": meta["delays_seconds"],
                "delays": json.loads((folder / "delays.json").read_text(encoding="utf-8"))}
    else:
        raise ValueError(f"configurazione sconosciuta: {config}")
    run = g3b.prosimos(folder / "model.bpmn", folder / "scenario.json",
                       g3b.tool_args(prepared.cases, prepared.start, seed, replicas, out), out, replicas)
    timings = json.loads((out / "timings.json").read_text(encoding="utf-8"))
    cost |= {"simulation_seconds": timings["simulation_seconds"], "simulation_peak_mb": run.peak_mb, "val01": g3b.val01(folder)}
    return [out / f"sim_{r}.csv" for r in range(replicas)], cost


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--logs", nargs="*", help="chiavi dei log di sviluppo (default: tutti)")
    parser.add_argument("--configs", nargs="*", default=["simod", "simod_fixed_extr"], choices=list(CONFIGS))
    parser.add_argument("--phases", nargs="*", default=list(g3b.PHASES), choices=g3b.PHASES)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--replicas", type=int, default=PAPER_REPLICAS)
    parser.add_argument("--force", action="store_true", help="rifa' anche le misure gia' scritte")
    parser.add_argument("--retry-failed", action="store_true", help="riprova le configurazioni fallite")
    args = parser.parse_args(argv)
    if error := replicas_error(args.replicas):
        parser.error(error)

    logs = [log for log in protocol.development_logs() if not args.logs or log.key in args.logs]
    with protocol.selection_phase():
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
                    result = g3b.evaluate(config, prepared, seed=args.seed, replicas=args.replicas, simulate_fn=simulate,
                                          label=CONFIGS[config])
                    result["b3_2"] = "tests/simulation/benchmark/b3_2/run.py"
                    target = RESULTS / log.key / phase / f"{config}.json"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                    print(f"{log.key} {phase} {config}: {result['status']} ({time.time() - began:.0f} s)"
                          + (f" {result.get('reason', '')[:300]}" if result["status"] != "measured" else ""), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
