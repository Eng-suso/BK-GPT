"""G3b: benchmark dei motori scientifici sui log di sviluppo del protocollo (PROTO-01).

    tests/simulation/benchmark/g3b/setup_envs.sh          # venv di ricerca, una volta
    uv run python tests/simulation/benchmark/g3b/run.py [--logs K ...] [--configs C ...] [--phases validation test]
    uv run python tests/simulation/benchmark/g3b/report.py   # tabelle e verdetti delle schede

Tutto gira dentro ``protocol.selection_phase()`` e legge i log da
``protocol.development_logs()``: gli holdout restano chiusi. Per ogni log due fasi:

- ``validation``: scoperta sul fit (train meno l'ultimo 20% dei casi), previsione della
  validazione (``protocol.train_validation``). Qui si sceglie;
- ``test``: scoperta sull'intero train, previsione del test.

Ogni configurazione produce 10 repliche (seed ``20261124 + replica``) con tanti casi
quanti il periodo da prevedere, dal suo primo inizio, e si misura con le sei distanze
di B2 (``log_distance.py``), media e IC 95%. Accanto: tempo di discovery, tempo di
simulazione per replica e picco di memoria (somma della memoria residente dell'albero
dei processi, campionata ogni 0,2 s). Il codice esterno gira come sottoprocesso nei
venv di ricerca (``/var/tmp/delir-g3b/envs``) e riceve solo percorsi di log di sviluppo.

Un risultato per file in ``results/<log>/<fase>/<configurazione>.json``, senza orari
nelle metriche: una misura gia' scritta non si rifa' (``--force`` per rifarla).
Fuori budget (PROTOCOL.md §6) = ``status: out_of_budget`` con tempo e memoria misurati.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import random
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

if __package__ in (None, ""):  # lanciato come script
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

import psutil

from tests.simulation.benchmark import protocol
from tests.simulation.benchmark.benchmark_datasets import DATASETS, fetch, load
from tests.simulation.benchmark.eval_harness import DEFAULT_SEED, PAPER_REPLICAS, summarize
from tests.simulation.benchmark.log_distance import METRICS, Event, cases, distances, parse_instant
from tests.simulation.benchmark.run_baseline import NaiveTwin, split_in_half

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
TOOLS = HERE / "tools"
STATE = Path(os.environ.get("G3B_DIR", "/var/tmp/delir-g3b"))
ENVS = STATE / "envs"
WORK = STATE / "work"
CACHE = Path(os.environ.get("DELIR_DATASETS_CACHE", Path.home() / ".cache" / "delir-datasets"))
PHASES = ("validation", "test")

# Budget del §6.
DISCOVERY_SECONDS = 2 * 3600
PEAK_MB = 12 * 1024
REPLICA_SECONDS = 600


# --------------------------------------------------------------------------- log


@dataclass(frozen=True, slots=True)
class Row:
    case_id: str
    activity: str
    resource: str
    start: datetime | None
    end: datetime

    def event(self) -> Event:
        return Event(self.case_id, self.activity, self.start or self.end, self.end)


def _csv_rows(path: Path) -> list[Row]:
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        return [
            Row(r["case_id"], r["activity"], r.get("resource") or "", parse_instant(r["start_time"]) if r.get("start_time") else None,
                parse_instant(r["end_time"]))
            for r in csv.DictReader(handle)
        ]


def _split(rows: list[Row]) -> tuple[list[Row], list[Row]]:
    period_a, _, _ = split_in_half([r.event() for r in rows])
    first = {e.case_id for e in period_a}
    return [r for r in rows if r.case_id in first], [r for r in rows if r.case_id not in first]


def periods(log: protocol.DevelopmentLog) -> tuple[list[Row], list[Row], ZoneInfo]:
    """Train e test del log come nel protocollo (§5), con le risorse che servono agli strumenti."""
    if log.key in DATASETS:
        dataset = DATASETS[log.key]
        event_log, _ = load(fetch(dataset), dataset.mapping)
        rows = [
            Row(e.case_id, e.activity, e.resource or "", e.start.astimezone(UTC) if e.start else None, e.end.astimezone(UTC))
            for e in event_log.events
        ]
        return (*_split(rows), ZoneInfo(dataset.mapping.timestamps.timezone))
    if "{train,test}" in log.source:
        train, test = (_csv_rows(protocol.ROOT / log.source.replace("{train,test}", part)) for part in ("train", "test"))
        return train, test, ZoneInfo("UTC")
    return (*_split(_csv_rows(protocol.ROOT / log.source)), ZoneInfo("UTC"))


@dataclass(frozen=True, slots=True)
class Prepared:
    log: protocol.DevelopmentLog
    phase: str
    source: list[Row]  # l'input della discovery
    target: list[Event]  # il periodo da prevedere
    zone: ZoneInfo
    work: Path
    identifiability: dict

    @property
    def cases(self) -> int:
        return len({e.case_id for e in self.target})

    @property
    def start(self) -> datetime:
        return min(e.start for e in self.target)

    @property
    def input_csv(self) -> Path:
        return self.work / "input.csv"


def prepare(log: protocol.DevelopmentLog, phase: str) -> Prepared:
    train, test, zone = periods(log)
    if phase == "validation":
        fit, validation = protocol.train_validation([r.event() for r in train])
        fit_cases = {e.case_id for e in fit}
        source, target = [r for r in train if r.case_id in fit_cases], validation
        # Proprieta' del §4 con A = fit e B = validazione.
        props = protocol.properties(
            fit, validation, has_start=[r.start is not None for r in train], has_resource=[bool(r.resource) for r in train]
        )
    else:
        source, target = train, [r.event() for r in test]
        everything = train + test
        props = protocol.properties(
            [r.event() for r in train], target,
            has_start=[r.start is not None for r in everything], has_resource=[bool(r.resource) for r in everything],
        )
    verdicts = protocol.identifiability(props, synthetic=log.category == protocol.SYNTHETIC)
    work = WORK / log.key / phase
    work.mkdir(parents=True, exist_ok=True)
    prepared = Prepared(log, phase, source, target, zone, work, {m: v for m, (v, _) in verdicts.items()})
    _write_input(prepared)
    return prepared


def _write_input(prepared: Prepared) -> None:
    """L'input della discovery per gli strumenti esterni: id dei casi interi, istanti ISO in UTC.

    Un inizio mancante resta vuoto (SIMOD lo stima; gli altri strumenti usano la fine).
    """
    ids = {case: n for n, case in enumerate(sorted({r.case_id for r in prepared.source}))}
    rows = sorted(prepared.source, key=lambda r: (ids[r.case_id], r.start or r.end, r.end))
    with open(prepared.input_csv, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["case_id", "activity", "resource", "start_time", "end_time"])
        for r in rows:
            writer.writerow([ids[r.case_id], r.activity, r.resource or "missing", r.start.isoformat() if r.start else "", r.end.isoformat()])


# --------------------------------------------------------------------------- sottoprocessi misurati


@dataclass(frozen=True, slots=True)
class Measured:
    seconds: float
    peak_mb: float
    returncode: int
    over_budget: str | None  # perche' e' stato fermato, se lo e' stato


def measured(cmd: list[str], *, cwd: Path, log_path: Path, timeout: float) -> Measured:
    """Lancia ``cmd`` misurando tempo reale e picco di memoria dell'albero dei processi."""
    began = time.perf_counter()
    peak = 0
    reason = None
    with open(log_path, "w", encoding="utf-8") as out:
        process = psutil.Popen(cmd, cwd=cwd, stdout=out, stderr=subprocess.STDOUT)
        while process.poll() is None:
            try:
                tree = [process, *process.children(recursive=True)]
                peak = max(peak, sum(p.memory_info().rss for p in tree if p.is_running()))
            except psutil.Error:
                pass
            if time.perf_counter() - began > timeout:
                reason = f"oltre {timeout:.0f} s"
            elif peak > PEAK_MB * 2**20:
                reason = f"oltre {PEAK_MB} MB"
            if reason:
                for p in [*process.children(recursive=True), process]:
                    try:
                        p.kill()
                    except psutil.Error:
                        pass
                process.wait()
                break
            time.sleep(0.2)
    return Measured(round(time.perf_counter() - began, 1), round(peak / 2**20, 1), process.returncode, reason)


def _python(env: str) -> str:
    return str(ENVS / env / "bin" / "python")


def _failed(step: str, run: Measured, log_path: Path) -> RuntimeError:
    tail = log_path.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-5:]
    return RuntimeError(f"{step}: uscita {run.returncode}; " + " | ".join(tail))


class OutOfBudget(Exception):
    def __init__(self, step: str, run: Measured):
        super().__init__(f"{step}: {run.over_budget}")
        self.run = run


def _checked(step: str, run: Measured, log_path: Path) -> Measured:
    if run.over_budget:
        raise OutOfBudget(step, run)
    if run.returncode != 0:
        raise _failed(step, run, log_path)
    return run


# --------------------------------------------------------------------------- discovery (in cache per log e fase)


def _cached(prepared: Prepared, name: str, build) -> dict:
    folder = prepared.work / name
    meta = folder / "meta.json"
    if meta.is_file():
        return json.loads(meta.read_text(encoding="utf-8"))
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    result = build(folder)
    meta.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def _simod(prepared: Prepared, variant: str, model: Path | None = None) -> dict:
    def build(folder: Path) -> dict:
        template = (HERE / "configs" / f"simod_{variant}.yml").read_text(encoding="utf-8")
        config = folder / "config.yml"
        config.write_text(template.replace("{train}", str(prepared.input_csv)).replace("{model}", str(model)), encoding="utf-8")
        log_path = folder / "simod.log"
        run = _checked(
            f"SIMOD {variant}",
            measured([str(ENVS / "simod" / "bin" / "simod"), "--configuration", str(config), "--output", str(folder / "out")],
                     cwd=folder, log_path=log_path, timeout=DISCOVERY_SECONDS),
            log_path,
        )
        best = folder / "out" / "best_result"
        shutil.copy(next(best.glob("*.bpmn")), folder / "model.bpmn")
        shutil.copy(next(p for p in best.glob("*.json") if p.name not in ("runtimes.json", "canonical_model.json")),
                    folder / "scenario.json")
        shutil.rmtree(folder / "out", ignore_errors=True)  # i file intermedi di SIMOD occupano GB
        return {"seconds": run.seconds, "peak_mb": run.peak_mb}

    return _cached(prepared, f"simod_{variant}", build)


def simod_diff(prepared: Prepared) -> tuple[Path, dict]:
    meta = _simod(prepared, "diff")
    return prepared.work / "simod_diff", meta


def simod_extr(prepared: Prepared) -> tuple[Path, dict]:
    diff_folder, diff = simod_diff(prepared)
    extr = _simod(prepared, "extr", diff_folder / "model.bpmn")
    # Riusa il BPMN della variante senza ritardi: il suo tempo conta (vedi schede in LOG.md).
    return prepared.work / "simod_extr", {"seconds": diff["seconds"] + extr["seconds"], "peak_mb": max(diff["peak_mb"], extr["peak_mb"])}


def atkde(prepared: Prepared, seed: int, replicas: int) -> tuple[Path, dict]:
    def build(folder: Path) -> dict:
        out = folder / "arrivals.json"
        log_path = folder / "atkde.log"
        run = _checked(
            "AT-KDE",
            measured([_python("atkde"), str(TOOLS / "atkde_arrivals.py"), "--input", str(prepared.input_csv), "--cases",
                      str(prepared.cases), "--start", prepared.start.isoformat(), "--seed", str(seed), "--replicas", str(replicas),
                      "--out", str(out)], cwd=CACHE / "at-kde", log_path=log_path, timeout=DISCOVERY_SECONDS),
            log_path,
        )
        return {"seconds": run.seconds, "peak_mb": run.peak_mb}

    meta = _cached(prepared, f"atkde_{seed}_{replicas}", build)
    return prepared.work / f"atkde_{seed}_{replicas}" / "arrivals.json", meta


# --------------------------------------------------------------------------- simulazione


def read_simulated(path: Path) -> list[Event]:
    """Un log simulato, qualunque strumento l'abbia scritto (colonne di Prosimos, ProSiT o AgentSimulator)."""
    with open(path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return []
    keys = rows[0].keys()
    activity = "activity" if "activity" in keys else "activity_name"
    start = "start_time" if "start_time" in keys else "start_timestamp"
    end = "end_time" if "end_time" in keys else "end_timestamp"
    events = [Event(str(r["case_id"]), r[activity], parse_instant(r[start]), parse_instant(r[end])) for r in rows if r[activity] != "zzz_end"]
    return events


def val01(folder: Path) -> str:
    """VAL-01 sullo scenario scoperto: lo stesso controllo dell'import del prodotto (``require_sound``)."""
    from backend.simulation.ir.from_prosimos import import_prosimos
    from backend.simulation.ir.soundness import UnsoundProcessError

    scenario = json.loads((folder / "scenario.json").read_text(encoding="utf-8"))
    try:
        import_prosimos(scenario, (folder / "model.bpmn").read_text(encoding="utf-8"))
    except UnsoundProcessError as exc:
        return f"non supera: {exc}"[:500]
    except ValueError as exc:
        return f"non importabile: {exc}"[:500]
    return "supera"


def _prosimos(prepared: Prepared, folder: Path, out: Path, seed: int, replicas: int, *extra: str) -> Measured:
    log_path = out / "prosimos.log"
    return _checked(
        "Prosimos",
        measured([_python("simod"), str(TOOLS / "prosimos_sim.py"), "--bpmn", str(folder / "model.bpmn"), "--json",
                  str(folder / "scenario.json"), "--cases", str(prepared.cases), "--start", prepared.start.isoformat(),
                  "--seed", str(seed), "--replicas", str(replicas), "--out", str(out), *extra],
                 cwd=out, log_path=log_path, timeout=REPLICA_SECONDS * replicas),
        log_path,
    )


def _replay_arrivals(prepared: Prepared, seed: int, replicas: int, out: Path) -> Path:
    """Gli arrivi del gemello "B = A": i casi del fit/train spostati sul periodo da prevedere."""
    twin = NaiveTwin.of([r.event() for r in prepared.source], prepared.target, prepared.zone)
    arrivals = []
    for replica in range(replicas):
        starts = cases(twin.replica(random.Random(seed + replica)))
        instants = sorted(min(e.start for e in group) for group in starts.values())
        arrivals.append([max(i, prepared.start).isoformat() for i in instants])
    path = out / "arrivals.json"
    path.write_text(json.dumps(arrivals), encoding="utf-8")
    return path


def _external(prepared: Prepared, env: str, tool: str, cwd: Path, out: Path, seed: int, replicas: int, *extra: str) -> tuple[dict, Measured]:
    log_path = out / f"{env}.log"
    run = _checked(
        tool,
        measured([_python(env), str(TOOLS / tool), "--input", str(prepared.input_csv), "--cases", str(prepared.cases),
                  "--start", prepared.start.isoformat(), "--seed", str(seed), "--replicas", str(replicas), "--out", str(out), *extra],
                 cwd=cwd, log_path=log_path, timeout=DISCOVERY_SECONDS + REPLICA_SECONDS * replicas),
        log_path,
    )
    return json.loads((out / "timings.json").read_text(encoding="utf-8")), run


def simulate(config: str, prepared: Prepared, out: Path, seed: int, replicas: int) -> tuple[list[list[Event]], dict]:
    """Le repliche simulate della configurazione e i loro costi."""
    if config == "naive":
        began = time.perf_counter()
        twin = NaiveTwin.of([r.event() for r in prepared.source], prepared.target, prepared.zone)
        logs, seconds = [], []
        for replica in range(replicas):
            tick = time.perf_counter()
            logs.append(twin.replica(random.Random(seed + replica)))
            seconds.append(round(time.perf_counter() - tick, 3))
        return logs, {"discovery_seconds": round(time.perf_counter() - began - sum(seconds), 3), "simulation_seconds": seconds}

    if config.startswith("simod"):
        folder, meta = (simod_diff if config == "simod" else simod_extr)(prepared)
        extra: list[str] = []
        cost = {"discovery_seconds": meta["seconds"], "discovery_peak_mb": meta["peak_mb"]}
        if config == "simod_extr_atkde":
            arrivals, kde = atkde(prepared, seed, replicas)
            extra = ["--arrivals", str(arrivals)]
            cost = {"discovery_seconds": meta["seconds"] + kde["seconds"], "discovery_peak_mb": max(meta["peak_mb"], kde["peak_mb"])}
        elif config == "simod_extr_replay":
            extra = ["--arrivals", str(_replay_arrivals(prepared, seed, replicas, out))]
        elif config == "simod_extr_247":
            extra = ["--calendars-247"]
        run = _prosimos(prepared, folder, out, seed, replicas, *extra)
        timings = json.loads((out / "timings.json").read_text(encoding="utf-8"))
        cost |= {"simulation_seconds": timings["simulation_seconds"], "simulation_peak_mb": run.peak_mb, "val01": val01(folder)}
    elif config in ("prosit", "prosit_norules"):
        depth = "3" if config == "prosit" else "0"
        timings, run = _external(prepared, "prosit", "prosit_run.py", out, out, seed, replicas, "--depth", depth)
        cost = {"discovery_seconds": timings["discovery_seconds"], "simulation_seconds": timings["simulation_seconds"], "peak_mb": run.peak_mb}
    elif config == "agentsim":
        timings, run = _external(prepared, "agentsim", "agentsim_run.py", CACHE / "agentsimulator", out, seed, replicas)
        cost = {"discovery_seconds": timings["discovery_seconds"], "simulation_seconds": timings["simulation_seconds"],
                "peak_mb": run.peak_mb, "choice": timings.get("choice")}
    else:
        raise ValueError(f"configurazione sconosciuta: {config}")
    return [read_simulated(out / f"sim_{r}.csv") for r in range(replicas)], cost


CONFIGS = {
    "naive": '"B = A" (gemello ingenuo di SIM-36)',
    "simod": "SIMOD, calendari fissi",
    "simod_extr": "SIMOD con ritardi estranei",
    "simod_extr_atkde": "SIMOD con ritardi estranei + arrivi AT-KDE",
    "simod_extr_replay": "SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi)",
    "simod_extr_247": "SIMOD con ritardi estranei, calendari 24/7 (ablazione)",
    "prosit": "ProSiT con regole (profondita' 3)",
    "prosit_norules": "ProSiT senza regole (profondita' 0)",
    "agentsim": "AgentSimulator (scelta automatica)",
}


def evaluate(config: str, prepared: Prepared, *, seed: int, replicas: int) -> dict:
    out = prepared.work / "runs" / config
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    base = {
        "g3b": "tests/simulation/benchmark/g3b/run.py",
        "log": prepared.log.key,
        "category": prepared.log.category,
        "phase": prepared.phase,
        "config": config,
        "label": CONFIGS[config],
        "seed": seed,
        "replicas": replicas,
        "cases": {"source": len({r.case_id for r in prepared.source}), "target": prepared.cases},
        "identifiability": prepared.identifiability,
    }
    try:
        logs, cost = simulate(config, prepared, out, seed, replicas)
    except OutOfBudget as exc:
        return {**base, "status": "out_of_budget", "reason": str(exc), "cost": {"seconds": exc.run.seconds, "peak_mb": exc.run.peak_mb}}
    except (RuntimeError, OSError, StopIteration) as exc:
        return {**base, "status": "failed", "reason": str(exc)[:2000]}
    if any(not log for log in logs):
        return {**base, "status": "failed", "reason": "una replica senza eventi", "cost": cost}
    if any(s > REPLICA_SECONDS for s in cost.get("simulation_seconds", [])):
        return {**base, "status": "out_of_budget", "reason": f"replica oltre {REPLICA_SECONDS} s", "cost": cost}
    measured_ = [distances(prepared.target, log) for log in logs]
    shutil.rmtree(out / "agentsim", ignore_errors=True)
    return {
        **base,
        "status": "measured",
        "simulated_cases": [len({e.case_id for e in log}) for log in logs],
        "metrics": {m: summarize([d[m] for d in measured_]) for m in METRICS},
        "cost": cost,
    }


def _done(path: Path) -> bool:
    """Misurato o fuori budget: non si rifa'. Un errore si riprova al giro dopo."""
    return path.is_file() and json.loads(path.read_text(encoding="utf-8"))["status"] in ("measured", "out_of_budget")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--logs", nargs="*", help="chiavi dei log di sviluppo (default: tutti)")
    parser.add_argument("--configs", nargs="*", default=list(CONFIGS), choices=list(CONFIGS))
    parser.add_argument("--phases", nargs="*", default=list(PHASES), choices=PHASES)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--replicas", type=int, default=PAPER_REPLICAS)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    logs = [log for log in protocol.development_logs() if not args.logs or log.key in args.logs]
    with protocol.selection_phase():
        for log in logs:
            for phase in args.phases:
                todo = [c for c in args.configs if args.force or not _done(RESULTS / log.key / phase / f"{c}.json")]
                if not todo:
                    continue
                prepared = prepare(log, phase)
                for config in todo:
                    began = time.time()
                    result = evaluate(config, prepared, seed=args.seed, replicas=args.replicas)
                    target = RESULTS / log.key / phase / f"{config}.json"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                    print(f"{log.key} {phase} {config}: {result['status']} ({time.time() - began:.0f} s)"
                          + (f" {result.get('reason', '')[:300]}" if result["status"] != "measured" else ""), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
