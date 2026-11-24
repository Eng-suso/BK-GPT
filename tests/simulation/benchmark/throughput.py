"""B6: lo script di carico del simulatore, sul percorso del prodotto.

    scripts/vpt_stack.sh start && eval "$(scripts/vpt_stack.sh env)"
    uv run python tests/simulation/benchmark/throughput.py            # 1, 2 e 4 worker, 3 giri ciascuno
    uv run python tests/simulation/benchmark/throughput.py --workers 4 --rounds 1 --out /tmp/b6

Per ogni numero di worker del runner avvia un runner Prosimos 2.1 (gunicorn con
quei worker) e un'API vera (uvicorn, ``backend.app``) con altrettanti run
insieme (``SIMULATION_MAX_CONCURRENT_RUNS``), sul Postgres dello stack. Poi
chiede un what-if come lo chiede il pannello: ``POST simulation-runs`` con 10
ripetizioni da 1.000 casi, scenario e seed fissi. Il tempo totale va dalla
richiesta all'ultimo risultato riletto dall'API (KPI e log degli eventi).

Lo scenario e' ``Loan_Application`` dei sintetici del paper (17 attivita', 11
gateway, sei ruoli con calendari): ``datasets/extraneous-delays/inputs/synthetic``.

Le fasi vengono dalla riga che il worker scrive per ogni run (``_PhaseTimer``):
in coda, motore, analisi del log, salvataggio. Le impronte (SHA-256 dei KPI e
del log di ogni ripetizione) dimostrano che i risultati non cambiano fra un
numero di worker e l'altro, fra un giro e l'altro e, con ``--check``, rispetto
al riferimento salvato in ``b6/fingerprints.json``.

Scrive in ``--out`` (default ``tests/simulation/benchmark/b6``):
``throughput.json`` (tutte le misure), ``throughput.md`` (la tabella) e, con
``--save-fingerprints``, ``fingerprints.json``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import statistics
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SCENARIO = ROOT / "datasets" / "extraneous-delays" / "inputs" / "synthetic" / "Loan_Application"
RUNNER_DIR = ROOT / "ops" / "prosimos" / "runner"
STACK = Path(os.environ.get("VPT_STACK_DIR", "/var/tmp/delir-vpt-stack"))
DEFAULT_OUT = HERE / "b6"

SEED = 20261124
REPLICAS = 10
CASES = 1000
START = "2026-01-05T08:00:00+00:00"
# La meta di B6: il what-if intero sotto il minuto.
TARGET_SECONDS = 60.0
_TIMEOUT_SECONDS = 900.0
_POLL_SECONDS = 0.2
_PHASE_LINE = re.compile(r"simulazione (\d+): (.*)$")
# Costo orario per ruolo: il JSON del paper li ha a zero, il what-if di un cliente no.
_COST_PER_HOUR = {"Applicant": 0.0, "Clerk": 32.0, "Loan Officer": 45.0, "Senior Officer": 60.0,
                  "Appraiser": 50.0, "AML Investigator": 55.0}


def _clock(value: str) -> str:
    return value[:8]  # "09:00:00.646" -> "09:00:00": il pannello lavora al secondo


def _periods(periods: list[dict]) -> list[dict]:
    return [{"from_day": p["from"], "to_day": p["to"], "begin": _clock(p["beginTime"]), "end": _clock(p["endTime"])}
            for p in periods]


def _duration(name: str, params: list[dict]) -> dict:
    values = [float(p["value"]) for p in params]
    if name == "fix":
        return {"distribution": "fixed", "mean_seconds": values[0]}
    if name == "expon":
        return {"distribution": "expon", "mean_seconds": values[0], "min_seconds": values[1], "max_seconds": values[2]}
    raise ValueError(f"distribuzione non prevista nello scenario fisso: {name}")


def whatif_request() -> dict:
    """Il corpo che il pannello manda per il what-if: lo scenario del paper nei campi di DeliR."""
    source = json.loads(SCENARIO.with_suffix(".json").read_text(encoding="utf-8"))
    calendars = [{"id": c["id"], "name": c["name"], "periods": _periods(c["time_periods"])}
                 for c in source["resource_calendars"]]
    calendars.append({"id": "arrivi", "name": "Arrivi", "periods": _periods(source["arrival_time_calendar"])})
    resources = []
    for profile in source["resource_profiles"]:
        (member,) = profile["resource_list"]
        resources.append({
            "id": member["id"], "name": profile["name"], "amount": int(member["amount"]),
            "cost_per_hour": _COST_PER_HOUR[profile["name"]], "calendar_id": member["calendar"],
        })
    tasks = []
    for task in source["task_resource_distribution"]:
        (assignment,) = task["resources"]
        tasks.append({"element_id": task["task_id"], "resource_id": assignment["resource_id"],
                      **_duration(assignment["distribution_name"], assignment["distribution_params"])})
    gateways = [{"element_id": g["gateway_id"],
                 "branches": [{"flow_id": p["path_id"], "probability": float(p["value"])} for p in g["probabilities"]]}
                for g in source["gateway_branching_probabilities"]]
    arrival = _duration(source["arrival_time_distribution"]["distribution_name"],
                        source["arrival_time_distribution"]["distribution_params"])
    return {
        "scenario_name": "B6 what-if",
        "current_bpmn_xml": SCENARIO.with_suffix(".bpmn").read_text(encoding="utf-8"),
        "total_cases": CASES,
        "replications": REPLICAS,
        "seed": SEED,
        "start_date": START,
        "arrival": {**arrival, "calendar_id": "arrivi"},
        "calendars": calendars,
        "resources": resources,
        "tasks": tasks,
        "gateways": gateways,
    }


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _wait_healthy(url: str, process: subprocess.Popen, log: Path) -> None:
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"{url}: il processo e' uscito ({process.returncode}), vedi {log}")
        try:
            if httpx.get(url, timeout=2).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    raise TimeoutError(f"{url} non risponde dopo 120 s, vedi {log}")


def _stop(process: subprocess.Popen) -> None:
    process.terminate()
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


_LOG_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}},
    "handlers": {"out": {"class": "logging.StreamHandler", "formatter": "plain", "stream": "ext://sys.stderr"}},
    "loggers": {"backend.simulation.service": {"level": "INFO", "handlers": ["out"], "propagate": False}},
    "root": {"level": "WARNING", "handlers": ["out"]},
}


@contextmanager
def product_stack(workers: int, work: Path):
    """Runner con ``workers`` worker e API che ne usa altrettanti, finche' serve."""
    runner_venv = STACK / "runner-venv"
    if not (runner_venv / "bin" / "gunicorn").exists():
        raise SystemExit(f"manca il runner in {runner_venv}: lancia scripts/vpt_stack.sh start")
    if not os.environ.get("WORKSPACE_DATABASE_URL"):
        raise SystemExit('manca il database: eval "$(scripts/vpt_stack.sh env)"')
    runner_port, api_port = _free_port(), _free_port()
    runner_log, api_log = work / f"runner-{workers}.log", work / f"api-{workers}.log"
    log_config = work / "logging.json"
    log_config.write_text(json.dumps(_LOG_CONFIG), encoding="utf-8")
    runner = subprocess.Popen(
        [str(runner_venv / "bin" / "gunicorn"), "--bind", f"127.0.0.1:{runner_port}", "--workers", str(workers),
         "--timeout", "1800", "runner:app"],
        cwd=RUNNER_DIR, env={**os.environ, "RUNNER_DATA_DIR": str(work / "runner-data")},
        stdout=runner_log.open("w"), stderr=subprocess.STDOUT,
    )
    api = None
    try:
        _wait_healthy(f"http://127.0.0.1:{runner_port}/health", runner, runner_log)
        api = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "backend.app:app", "--host", "127.0.0.1", "--port", str(api_port),
             "--workers", "1", "--log-config", str(log_config), "--no-access-log"],
            cwd=ROOT,
            env={**os.environ, "PROSIMOS_BASE_URL": f"http://127.0.0.1:{runner_port}",
                 "SIMULATION_MAX_CONCURRENT_RUNS": str(workers)},
            stdout=api_log.open("w"), stderr=subprocess.STDOUT,
        )
        _wait_healthy(f"http://127.0.0.1:{api_port}/health", api, api_log)
        yield f"http://127.0.0.1:{api_port}", api_log
    finally:
        if api is not None:
            _stop(api)
        _stop(runner)


def _ok(response: httpx.Response) -> httpx.Response:
    if response.status_code != 200:
        raise RuntimeError(f"{response.request.method} {response.request.url.path}: {response.status_code} {response.text[:500]}")
    return response


def _new_process(client: httpx.Client, label: str) -> str:
    client_id = _ok(client.post("/v1/workspace/clients", json={"name": f"B6 {label}"})).json()["id"]
    project_id = _ok(client.post("/v1/workspace/projects", json={"client_id": client_id, "name": f"B6 {label}"})).json()["id"]
    return _ok(client.post(f"/v1/workspace/projects/{project_id}/processes", json={"name": f"B6 Loan application {label}"})).json()[
        "bpmn_model_id"
    ]


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def whatif(base_url: str, body: dict, label: str) -> dict:
    """Un what-if dalla richiesta all'ultimo risultato riletto; tempi e impronte."""
    with httpx.Client(base_url=base_url, timeout=120) as client:
        bpmn_model_id = _new_process(client, label)
        url = f"/v1/workspace/bpmn-models/{bpmn_model_id}/simulation-runs"
        started = time.perf_counter()
        _ok(client.post(url, json=body))
        accepted = time.perf_counter() - started
        deadline = time.monotonic() + _TIMEOUT_SECONDS
        while True:
            runs = _ok(client.get(url)).json()
            failed = [r for r in runs if r["status"] == "failed"]
            if failed:
                raise RuntimeError(f"run {failed[0]['id']} fallito: {failed[0].get('error')}")
            if len(runs) == REPLICAS and all(r["status"] == "completed" for r in runs):
                break
            if time.monotonic() > deadline:
                raise TimeoutError(f"what-if {label}: non finito dopo {_TIMEOUT_SECONDS:g} s")
            time.sleep(_POLL_SECONDS)
        completed = time.perf_counter() - started
        runs.sort(key=lambda r: r["request"]["replication_index"])
        # Prima i KPI, come li legge il pannello; poi i log, come li scarica il consulente.
        kpis = [_ok(client.get(f"/v1/workspace/simulation-runs/{run['id']}")).json().get("summary") for run in runs]
        kpi_read = time.perf_counter() - started
        logs = [_ok(client.get(f"/v1/workspace/simulation-runs/{run['id']}/event-log", params={"format": "csv"})).text
                for run in runs]
        total = time.perf_counter() - started
        fingerprints = {}
        for run, kpi, log in zip(runs, kpis, logs, strict=True):
            if not kpi or not log:
                raise RuntimeError(f"run {run['id']}: KPI o log non leggibili")
            fingerprints[str(run["request"]["replication_index"])] = {
                "seed": run["request"]["seed"],
                "kpi": _digest(json.dumps(kpi, sort_keys=True)),
                "event_log": _digest(log),
            }
    return {
        "run_ids": [r["id"] for r in runs],
        "accepted_s": accepted, "completed_s": completed, "kpi_read_s": kpi_read, "total_s": total,
        "runs_per_minute": REPLICAS / total * 60, "fingerprints": fingerprints,
    }


def phases(api_log: Path, run_ids: list[int]) -> dict[str, dict[str, float]]:
    """Le fasi dei run di questo what-if, dalla riga di ``_PhaseTimer``: media e massimo."""
    wanted, seen = set(run_ids), {}
    for line in api_log.read_text(encoding="utf-8").splitlines():
        match = _PHASE_LINE.search(line)
        if match and int(match.group(1)) in wanted:
            for part in match.group(2).split(", "):
                name, seconds, _ = part.rsplit(" ", 2)
                seen.setdefault(name, []).append(float(seconds))
    if any(len(values) != len(wanted) for values in seen.values()) or not seen:
        raise RuntimeError(f"fasi mancanti nel log dell'API ({api_log}): {sorted(seen)}")
    return {name: {"mean": statistics.fmean(v), "max": max(v), "sum": sum(v)} for name, v in seen.items()}


def measure(worker_counts: list[int], rounds: int) -> list[dict]:
    body = whatif_request()
    results = []
    with tempfile.TemporaryDirectory(prefix="b6-") as tmp:
        for workers in worker_counts:
            with product_stack(workers, Path(tmp)) as (base_url, api_log):
                for round_ in range(1, rounds + 1):
                    measured = whatif(base_url, body, f"{workers}w-{round_}-{time.time_ns()}")
                    measured["phases"] = phases(api_log, measured["run_ids"])
                    measured.update(workers=workers, round=round_)
                    del measured["run_ids"]
                    results.append(measured)
                    print(f"{workers} worker, giro {round_}: {measured['total_s']:.1f} s, "
                          f"{measured['runs_per_minute']:.1f} run/min", file=sys.stderr, flush=True)
    return results


_PHASES = ("in coda", "motore", "analisi", "salvataggio")


def table(results: list[dict]) -> str:
    lines = [
        f"What-if: {REPLICAS} ripetizioni x {CASES} casi, scenario Loan_Application, seed {SEED}. "
        f"Meta: meno di {TARGET_SECONDS:g} s dalla richiesta al risultato riletto (KPI e log di tutte le ripetizioni).",
        "Tempi dall'invio della richiesta; le fasi sono la media per run.",
        "",
        "| Worker | Giro | Totale (s) | Run/min | Accettato (s) | Tutti completati (s) | KPI letti (s) | "
        + " | ".join(f"{p} (s)" for p in _PHASES) + " | Meta |",
        "| --- | --- | --- | --- | --- | --- | --- |" + " --- |" * len(_PHASES) + " --- |",
    ]
    for r in results:
        cells = " | ".join(f"{r['phases'][p]['mean']:.2f}" if p in r["phases"] else "-" for p in _PHASES)
        lines.append(
            f"| {r['workers']} | {r['round']} | {r['total_s']:.1f} | {r['runs_per_minute']:.1f} | {r['accepted_s']:.2f} "
            f"| {r['completed_s']:.1f} | {r['kpi_read_s']:.1f} | {cells} "
            f"| {'raggiunta' if r['total_s'] < TARGET_SECONDS else 'no'} |"
        )
    return "\n".join(lines) + "\n"


def same_results(results: list[dict], reference: dict | None) -> list[str]:
    """Le differenze di impronta fra i what-if (e verso il riferimento, se c'e')."""
    expected = reference or results[0]["fingerprints"]
    return [
        f"{r['workers']} worker, giro {r['round']}, ripetizione {index}"
        for r in results
        for index, print_ in r["fingerprints"].items()
        if print_ != expected.get(index)
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workers", type=int, nargs="+", default=[1, 2, 4])
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true", help="confronta le impronte con b6/fingerprints.json")
    parser.add_argument("--save-fingerprints", action="store_true", help="salva le impronte come riferimento")
    args = parser.parse_args(argv)
    if args.rounds < 1 or any(w < 1 for w in args.workers):
        parser.error("--rounds e --workers vanno da 1 in su")

    reference_path = DEFAULT_OUT / "fingerprints.json"
    reference = json.loads(reference_path.read_text(encoding="utf-8"))["replicas"] if args.check else None
    results = measure(args.workers, args.rounds)
    differences = same_results(results, reference)

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "throughput.json").write_text(
        json.dumps({"scenario": "Loan_Application", "replicas": REPLICAS, "cases": CASES, "seed": SEED,
                    "cpus": os.cpu_count(), "results": results}, indent=2) + "\n",
        encoding="utf-8",
    )
    report = table(results)
    (args.out / "throughput.md").write_text(f"# Throughput del simulatore (B6)\n\n{report}", encoding="utf-8")
    if args.save_fingerprints and not differences:
        reference_path.parent.mkdir(parents=True, exist_ok=True)
        reference_path.write_text(
            json.dumps({"scenario": "Loan_Application", "seed": SEED, "cases": CASES,
                        "replicas": results[0]["fingerprints"]}, indent=2) + "\n",
            encoding="utf-8",
        )
    print(report)
    if differences:
        print("risultati diversi da " + ("riferimento" if reference else "primo what-if") + ": " + "; ".join(differences))
        return 1
    return 0 if all(r["total_s"] < TARGET_SECONDS for r in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
