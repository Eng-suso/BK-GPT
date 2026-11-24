"""B2: l'harness di valutazione del simulatore, sullo stack reale.

    scripts/vpt_stack.sh start && eval "$(scripts/vpt_stack.sh env)"
    uv run python tests/simulation/benchmark/eval_harness.py [--seed N] [--replicas 10] [scenario ...]

Per ognuno dei 19 scenari di ``datasets/extraneous-delays/inputs`` fa il percorso
del prodotto, senza mock: import con ``prosimos-import``, run dalla coda
(``simulation-model-runs``) eseguiti dal worker sul runner Prosimos 2.1, log
degli eventi e KPI riletti dal database tramite l'API. Ogni scenario si simula
cosi' com'e', con tanti casi quanti il log di riferimento e dal suo primo
inizio, come lo script di valutazione del paper.

Il log di riferimento e' il log di test per i 3 reali e il log del paper per i
16 sintetici. Le sei distanze (``log_distance.py``) si calcolano per replica e
si riassumono con media e intervallo t al 95%.

Scrive in ``--out`` (default ``tests/simulation/benchmark/b2``):

- ``baseline.json``: le metriche di ogni scenario. Nessun orario ne' id di run:
  con lo stesso seed il file e' identico bit per bit (meta 1 di B2);
- ``baseline.md``: le stesse metriche in tabella, media ± intervallo;
- ``paper-comparison.md``: DeliR contro la riga ``<log>_original`` del paper per
  RED, AED e W1 del cycle time, con "dentro" se lo scarto fra le medie e' minore
  della somma dei due intervalli (meta 2).
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

if __package__ in (None, ""):  # lanciato come script
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tests.simulation.benchmark.log_distance import (
    MAX_REPLICAS,
    METRICS,
    cycle_time_w1,
    distances,
    events_from_rows,
    mean_confidence_interval,
    parse_instant,
    read_csv_log,
)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
INPUTS = ROOT / "datasets" / "extraneous-delays" / "inputs"
PAPER_METRICS = ROOT / "datasets" / "extraneous-delays" / "paper-results" / "real-life-evaluation" / "metrics.csv"
PAPER_CYCLE_TIME = HERE / "fixtures" / "paper_original_cycle_time_w1.json"
DEFAULT_OUT = HERE / "b2"

REAL_LIFE = ("AcademicCredentials", "BPIC_2012_W", "BPIC_2017_W")
# Come il paper: 10 simulazioni per modello (``for i in range(10)``).
PAPER_REPLICAS = 10
DEFAULT_SEED = 20261124
# Le tre metriche che il paper pubblica (o da cui si ricava) per la riga ``original``.
PAPER_METRICS_COMPARED = ("relative_event", "absolute_event", "cycle_time_w1")
_RUN_TIMEOUT_SECONDS = 1800.0


@dataclass(frozen=True, slots=True)
class Scenario:
    name: str
    kind: str  # "real-life" o "synthetic"
    # Cartella con ``<name>.json`` e ``<name>.bpmn`` di uno scenario esterno (G3:
    # scoperto da SIMOD); senza, quello del dataset. Il log di riferimento non cambia.
    source: Path | None = None

    @property
    def model(self) -> Path:
        return (self.source or INPUTS / self.kind) / self.name

    @property
    def reference(self) -> Path:
        suffix = "_test.csv.gz" if self.kind == "real-life" else ".csv.gz"
        return INPUTS / self.kind / f"{self.name}{suffix}"


def scenarios() -> list[Scenario]:
    synthetic = sorted(p.stem for p in (INPUTS / "synthetic").glob("*.json"))
    return [Scenario(name, "real-life") for name in REAL_LIFE] + [Scenario(name, "synthetic") for name in synthetic]


class ProductPath:
    """Le chiamate che fa la UI: un processo, l'import, i run, il log e i KPI."""

    def __init__(self, client) -> None:
        self.client = client
        # Ogni passata ha clienti e processi suoi: la chiave d'idempotenza dei run
        # contiene il processo, quindi nessun run di una passata precedente torna indietro.
        self.session = uuid.uuid4().hex[:12]
        self.seen_runs: set[int] = set()

    def _checked(self, response):
        if response.status_code != 200:
            raise RuntimeError(f"{response.request.method} {response.request.url.path}: {response.status_code} {response.text[:500]}")
        return response

    def _ok(self, response) -> dict:
        return self._checked(response).json()

    def new_process(self, name: str) -> str:
        client_id = self._ok(self.client.post("/v1/workspace/clients", json={"name": f"B2 {self.session}"}))["id"]
        project_id = self._ok(
            self.client.post("/v1/workspace/projects", json={"client_id": client_id, "name": f"B2 {name} {self.session}"})
        )["id"]
        return self._ok(self.client.post(f"/v1/workspace/projects/{project_id}/processes", json={"name": f"B2 {name}"}))[
            "bpmn_model_id"
        ]

    def import_scenario(self, bpmn_model_id: str, scenario: dict, bpmn_xml: str) -> dict:
        return self._ok(
            self.client.post(
                f"/v1/workspace/bpmn-models/{bpmn_model_id}/prosimos-import",
                json={"scenario": scenario, "current_bpmn_xml": bpmn_xml},
            )
        )

    def run(self, bpmn_model_id: str, model: dict, bpmn_xml: str, *, cases: int, start: str, seed: int, key: str) -> dict:
        queued = self._ok(
            self.client.post(
                f"/v1/workspace/bpmn-models/{bpmn_model_id}/simulation-model-runs",
                json={
                    "model": model,
                    "current_bpmn_xml": bpmn_xml,
                    "total_cases": cases,
                    "start_date": start,
                    "seed": seed,
                    "scenario_name": "B2 as-is",
                },
            )
        )
        if queued["id"] in self.seen_runs:
            raise RuntimeError(f"run {queued['id']} ({key}) gia' visto: la coda non ha simulato di nuovo")
        self.seen_runs.add(queued["id"])
        deadline = time.monotonic() + _RUN_TIMEOUT_SECONDS
        while True:
            run = self._ok(self.client.get(f"/v1/workspace/simulation-runs/{queued['id']}"))
            if run["status"] == "completed":
                return run
            if run["status"] == "failed":
                raise RuntimeError(f"run {queued['id']} ({key}) fallito: {run.get('error')}")
            if time.monotonic() > deadline:
                raise TimeoutError(f"run {queued['id']} ({key}) ancora {run['status']} dopo {_RUN_TIMEOUT_SECONDS:g} s")
            time.sleep(0.5)

    def event_log(self, run_id: int) -> list[dict[str, str]]:
        response = self._checked(self.client.get(f"/v1/workspace/simulation-runs/{run_id}/event-log", params={"format": "csv"}))
        return list(csv.DictReader(io.StringIO(response.text)))


def check_same_log(kpi_cycle_avg: float, rows: list[dict[str, str]], label: str) -> None:
    """Il log riletto dall'API e' quello su cui il database ha calcolato i KPI.

    Il KPI di DeliR misura il caso dalla prima abilitazione (l'arrivo) all'ultima
    fine; le distanze del paper dal primo inizio. Qui serve la definizione del KPI.
    """
    by_case: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_case.setdefault(row["case_id"], []).append(row)
    cycles = [
        (max(parse_instant(r["end_time"]) for r in case) - min(parse_instant(r["enable_time"]) for r in case)).total_seconds()
        for case in by_case.values()
    ]
    from_log = math.fsum(cycles) / len(cycles)
    # Il CSV esportato arrotonda al microsecondo: lo scarto ammesso e' di quell'ordine.
    if abs(from_log - kpi_cycle_avg) > 1e-3:
        raise RuntimeError(f"{label}: cycle time medio {from_log} dal log, {kpi_cycle_avg} dai KPI")


def summarize(values: list[float]) -> dict:
    average, half = mean_confidence_interval(values)
    return {"mean": average, "ci95": half, "replicas": values}


def import_into_new_process(path: ProductPath, scenario: Scenario) -> tuple[str, dict]:
    """Un processo nuovo con lo scenario importato: id del modello BPMN e risposta dell'import."""
    bpmn_model_id = path.new_process(scenario.name)
    imported = path.import_scenario(
        bpmn_model_id,
        json.loads(scenario.model.with_suffix(".json").read_text(encoding="utf-8")),
        scenario.model.with_suffix(".bpmn").read_text(encoding="utf-8"),
    )
    return bpmn_model_id, imported


def evaluate(
    path: ProductPath, scenario: Scenario, *, seed: int, replicas: int, imported: tuple[str, dict] | None = None
) -> dict:
    """``imported``: il risultato di ``import_into_new_process``, se il chiamante ha gia' importato."""
    reference = read_csv_log(scenario.reference)
    cases = len({e.case_id for e in reference})
    start = min(e.start for e in reference).isoformat()
    bpmn_xml = scenario.model.with_suffix(".bpmn").read_text(encoding="utf-8")
    bpmn_model_id, imported = imported or import_into_new_process(path, scenario)

    measured: list[dict[str, float]] = []
    kpi_cycle: list[float] = []
    engine_versions: set[str] = set()
    for replica in range(replicas):
        run = path.run(
            bpmn_model_id, imported["model"], bpmn_xml,
            cases=cases, start=start, seed=seed + replica, key=f"{scenario.name}-{replica}",
        )
        version = (run.get("result") or {}).get("EngineVersion")
        if not version:
            raise RuntimeError(f"run {run['id']} ({scenario.name}): il runner non ha detto la versione del motore")
        engine_versions.add(str(version))
        summary = run.get("summary") or {}
        if summary.get("casesCompleted") != cases:
            raise RuntimeError(f"{scenario.name}: {summary.get('casesCompleted')} casi completati su {cases}")
        rows = path.event_log(run["id"])
        check_same_log(summary["cycle"]["avg"], rows, f"run {run['id']} ({scenario.name})")
        kpi_cycle.append(summary["cycle"]["avg"])
        measured.append(distances(reference, events_from_rows(rows)))

    return {
        "scenario": scenario.name,
        "kind": scenario.kind,
        "reference_log": scenario.reference.relative_to(ROOT).as_posix(),
        "cases": cases,
        "start": start,
        "seeds": [seed + r for r in range(replicas)],
        "engine_versions": sorted(engine_versions),
        "import_notes": len(imported.get("notes", [])),
        "metrics": {metric: summarize([m[metric] for m in measured]) for metric in METRICS},
        # Dal riepilogo del run nel database; ``check_same_log`` lo confronta con il log riletto.
        "kpi_cycle_time_avg_seconds": summarize(kpi_cycle),
    }


def paper_reference() -> dict[str, dict[str, tuple[float, float]]]:
    """Media e intervallo della riga ``<log>_original`` del paper per le tre metriche.

    RED e AED vengono da ``metrics.csv`` del paper. W1 del cycle time il paper
    non lo pubblica: si ricava dai suoi 10 log ``sim_original`` con le stesse
    formule (``--refresh-paper-cycle-time``), e il risultato sta in una fixture.
    """
    with PAPER_METRICS.open(newline="") as handle:
        rows = {row["name"]: row for row in csv.DictReader(handle)}
    cycle = json.loads(PAPER_CYCLE_TIME.read_text(encoding="utf-8"))["logs"]
    reference: dict[str, dict[str, tuple[float, float]]] = {}
    for log in REAL_LIFE:
        row = rows[f"{log}_original"]
        reference[log] = {
            "relative_event": (float(row["relative_mean"]), float(row["relative_cnf"])),
            "absolute_event": (float(row["absolute_mean"]), float(row["absolute_cnf"])),
            "cycle_time_w1": (cycle[log]["mean"], cycle[log]["ci95"]),
        }
    return reference


def within_intervals(ours: dict, reference: dict) -> bool:
    """Pari se lo scarto fra le medie e' minore della somma dei due intervalli (meta 2 di B2)."""
    return abs(ours["mean"] - reference["mean"]) < ours["ci95"] + reference["ci95"]


def compare_with_paper(results: list[dict]) -> list[dict]:
    paper = paper_reference()
    rows = []
    for result in results:
        if result["kind"] != "real-life":
            continue
        for metric in PAPER_METRICS_COMPARED:
            ours = result["metrics"][metric]
            paper_mean, paper_ci = paper[result["scenario"]][metric]
            rows.append({
                "log": result["scenario"], "metric": metric,
                "delir_mean": ours["mean"], "delir_ci95": ours["ci95"],
                "paper_mean": paper_mean, "paper_ci95": paper_ci,
                "gap": abs(ours["mean"] - paper_mean), "allowed": ours["ci95"] + paper_ci,
                "inside": within_intervals(ours, {"mean": paper_mean, "ci95": paper_ci}),
            })
    return rows


_LABELS = {"relative_event": "RED (ore)", "absolute_event": "AED (ore)", "cycle_time_w1": "W1 cycle time (ore)"}


def comparison_table(rows: list[dict]) -> str:
    lines = [
        "| Log | Metrica | DeliR (media ± IC 95%) | Paper (media ± IC 95%) | Scarto | Somma IC | Esito |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        lines.append(
            f"| {r['log']} | {_LABELS[r['metric']]} | {r['delir_mean']:.3f} ± {r['delir_ci95']:.3f} "
            f"| {r['paper_mean']:.3f} ± {r['paper_ci95']:.3f} | {r['gap']:.3f} | {r['allowed']:.3f} "
            f"| {'dentro' if r['inside'] else 'fuori'} |"
        )
    return "\n".join(lines) + "\n"


METRIC_LABELS = {
    "cycle_time_w1": "W1 cycle time (ore)", "ngram": "NGD", "relative_event": "RED (ore)",
    "absolute_event": "AED (ore)", "circadian_event": "CED (ore)", "case_arrival": "CAR (ore)",
}


def cell(summary: dict) -> str:
    """Media ± semiampiezza dell'intervallo al 95%."""
    return f"{summary['mean']:.3f} ± {summary['ci95']:.3f}"


def baseline_table(results: list[dict]) -> str:
    """Le sei metriche di ogni scenario, media ± intervallo: il riferimento di B3 e B5."""
    lines = [
        "| Scenario | " + " | ".join(METRIC_LABELS[m] for m in METRICS) + " |",
        "| --- |" + " --- |" * len(METRICS),
    ]
    for r in results:
        cells = " | ".join(cell(r["metrics"][m]) for m in METRICS)
        lines.append(f"| {r['scenario']} | {cells} |")
    return "\n".join(lines) + "\n"


def refresh_paper_cycle_time(outputs: Path) -> None:
    """Ricalcola W1 del cycle time dai 10 log ``sim_original`` del paper (cache di ``extraneous-delays-outputs``)."""
    logs = {}
    for log in REAL_LIFE:
        test = read_csv_log(INPUTS / "real-life" / f"{log}_test.csv.gz")
        logs[log] = summarize([
            cycle_time_w1(test, read_csv_log(outputs / log / f"{log}_sim_original_{i}.csv"))
            for i in range(PAPER_REPLICAS)
        ])
    PAPER_CYCLE_TIME.write_text(
        json.dumps({
            "source": "extraneous-delays-outputs (Zenodo 10.5281/zenodo.10435849), real-life-evaluation/<log>/<log>_sim_original_<0..9>.csv contro <log>_test.csv.gz",
            "metric": "cycle_time_distribution_distance, bin di un'ora, log-distance-measures 2.2 (port in log_distance.py)",
            "logs": logs,
        }, indent=2) + "\n",
        encoding="utf-8",
    )


def run(selected: list[Scenario], *, seed: int, replicas: int, out: Path) -> list[dict]:
    from fastapi.testclient import TestClient

    from backend.app import app

    results = []
    with TestClient(app) as client:
        path = ProductPath(client)
        for scenario in selected:
            started = time.perf_counter()
            results.append(evaluate(path, scenario, seed=seed, replicas=replicas))
            print(f"{scenario.name}: {time.perf_counter() - started:.1f} s", file=sys.stderr, flush=True)

    out.mkdir(parents=True, exist_ok=True)
    # Un file di una passata precedente non resta accanto a una passata diversa.
    (out / "paper-comparison.md").unlink(missing_ok=True)
    baseline = {
        "harness": "B2, tests/simulation/benchmark/eval_harness.py",
        "metrics": "log-distance-measures 2.2 (port in log_distance.py); tempi in ore, ngram in [0, 1]",
        "seed": seed,
        "replicas": replicas,
        "scenarios": results,
    }
    (out / "baseline.json").write_text(json.dumps(baseline, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "baseline.md").write_text(
        f"# Baseline B2 (seed {seed}, {replicas} repliche)\n\n" + baseline_table(results), encoding="utf-8"
    )
    rows = compare_with_paper(results)
    if rows:
        (out / "paper-comparison.md").write_text(
            f"# DeliR contro il paper (seed {seed}, {replicas} repliche)\n\n" + comparison_table(rows), encoding="utf-8"
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    names = [s.name for s in scenarios()]
    parser.add_argument("scenarios", nargs="*", choices=names, help="default: tutti i 19")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--replicas", type=int, default=PAPER_REPLICAS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--refresh-paper-cycle-time", type=Path, metavar="OUTPUTS",
                        help="ricalcola la fixture di W1 dal real-life-evaluation del paper ed esce")
    args = parser.parse_args(argv)
    if not 2 <= args.replicas <= MAX_REPLICAS:
        parser.error(f"--replicas va da 2 a {MAX_REPLICAS}: serve un intervallo di confidenza")
    if args.scenarios and args.out.resolve() == DEFAULT_OUT.resolve():
        parser.error("con una parte degli scenari indica --out: la baseline in b2/ e' quella dei 19")
    if args.refresh_paper_cycle_time:
        refresh_paper_cycle_time(args.refresh_paper_cycle_time)
        return 0

    selected = [s for s in scenarios() if not args.scenarios or s.name in args.scenarios]
    rows = run(selected, seed=args.seed, replicas=args.replicas, out=args.out)
    if rows:
        print(comparison_table(rows))
    return 0 if all(r["inside"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
