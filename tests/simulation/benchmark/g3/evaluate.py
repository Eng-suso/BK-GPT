"""G3: gli scenari scoperti da SIMOD, valutati sul log di test con l'harness di B2.

    scripts/vpt_stack.sh start && eval "$(scripts/vpt_stack.sh env)"
    tests/simulation/benchmark/g3/discover.sh all        # SIMOD, scenari in discovered/
    uv run python tests/simulation/benchmark/g3/evaluate.py [--seed N] [--replicas 10]

Per ogni log reale e ogni scenario in ``discovered/<log>_<variante>/`` fa il
percorso del prodotto di B2 (import con ``prosimos-import``, run dalla coda sul
runner Prosimos 2.1, log riletto dall'API), con lo stesso seed, le stesse 10
repliche e lo stesso log di test. Mette accanto:

- **scenario del paper**: lo scenario SIMOD del paper (``datasets/extraneous-delays``)
  sullo stesso percorso, preso da ``b2/baseline.json`` (stesso harness e seed), e la
  riga ``<log>_original`` pubblicata dal paper per RED, AED e W1;
- **gemello ingenuo** "B sara' come A": il log di train cosi' com'e', spostato di un
  numero intero di settimane perche' il primo caso parta nella settimana del primo
  caso di test (ore e giorni della settimana restano quelli veri). Non simula: e'
  deterministico, quindi il suo intervallo e' zero.

Scrive ``results.json`` e ``results.md`` in questa cartella.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

if __package__ in (None, ""):  # lanciato come script
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from tests.simulation.benchmark import eval_harness as harness
from tests.simulation.benchmark.log_distance import Event, distances, read_csv_log

HERE = Path(__file__).resolve().parent
DISCOVERED = HERE / "discovered"
B2_BASELINE = harness.DEFAULT_OUT / "baseline.json"
# Le metriche della tabella di G3: le tre del paper e l'arrivo dei casi.
COMPARED = ("relative_event", "absolute_event", "cycle_time_w1", "case_arrival")
LABELS = {"relative_event": "RED", "absolute_event": "AED", "cycle_time_w1": "W1 cycle time", "case_arrival": "CAR"}
WEEK = timedelta(weeks=1)


def naive_twin(train: list[Event], test: list[Event]) -> list[Event]:
    """Il log di train spostato di settimane intere verso il periodo di test."""
    shift = round((min(e.start for e in test) - min(e.start for e in train)) / WEEK) * WEEK
    return [replace(e, start=e.start + shift, end=e.end + shift) for e in train]


def naive_metrics(log: str) -> dict:
    folder = harness.INPUTS / "real-life"
    test = read_csv_log(folder / f"{log}_test.csv.gz")
    measured = distances(test, naive_twin(read_csv_log(folder / f"{log}_train.csv.gz"), test))
    return {metric: {"mean": value, "ci95": 0.0} for metric, value in measured.items()}


def discovered_scenarios() -> list[tuple[str, str, Path]]:
    found = []
    for log in harness.REAL_LIFE:
        for folder in sorted(DISCOVERED.glob(f"{log}_*")):
            if (folder / f"{log}.json").is_file():
                found.append((log, folder.name.removeprefix(f"{log}_"), folder))
    return found


def import_notes(path: harness.ProductPath, scenario: harness.Scenario) -> list[dict]:
    """Le note del report d'import: cosa DeliR ha dovuto adattare o dichiarare."""
    bpmn_xml = scenario.model.with_suffix(".bpmn").read_text(encoding="utf-8")
    imported = path.import_scenario(
        path.new_process(f"G3 {scenario.name}"),
        json.loads(scenario.model.with_suffix(".json").read_text(encoding="utf-8")),
        bpmn_xml,
    )
    return imported.get("notes", [])


def evaluate_all(*, seed: int, replicas: int) -> dict:
    from fastapi.testclient import TestClient

    from backend.app import app

    found = discovered_scenarios()
    if not found:
        raise SystemExit("nessuno scenario in discovered/: lancia prima discover.sh")
    simod = []
    with TestClient(app) as client:
        path = harness.ProductPath(client)
        for log, variant, folder in found:
            scenario = harness.Scenario(log, "real-life", source=folder)
            result = harness.evaluate(path, scenario, seed=seed, replicas=replicas)
            result["variant"] = variant
            result["import_notes"] = import_notes(path, scenario)
            result["discovery"] = json.loads((folder / "discovery.json").read_text(encoding="utf-8"))
            simod.append(result)
            print(f"{log} {variant}: valutato", file=sys.stderr, flush=True)

    b2 = json.loads(B2_BASELINE.read_text(encoding="utf-8"))
    if (b2["seed"], b2["replicas"]) != (seed, replicas):
        raise SystemExit(f"b2/baseline.json ha seed {b2['seed']} e {b2['replicas']} repliche: rilancia B2 o usa gli stessi")
    paper_in_delir = {r["scenario"]: r["metrics"] for r in b2["scenarios"] if r["kind"] == "real-life"}
    published = harness.paper_reference()
    return {
        "spike": "G3, tests/simulation/benchmark/g3/evaluate.py",
        "seed": seed,
        "replicas": replicas,
        "simod": simod,
        "paper_scenario_in_delir": paper_in_delir,
        "paper_published": {
            log: {m: {"mean": v[0], "ci95": v[1]} for m, v in metrics.items()} for log, metrics in published.items()
        },
        "naive_twin": {log: naive_metrics(log) for log in harness.REAL_LIFE},
    }


def _cell(value: dict | None) -> str:
    return "—" if value is None else f"{value['mean']:.2f} ± {value['ci95']:.2f}"


def _verdict(ours: dict, reference: dict) -> str:
    gap = ours["mean"] - reference["mean"]
    if abs(gap) < ours["ci95"] + reference["ci95"]:
        return "pari"
    return "meglio" if gap < 0 else "peggio"


VARIANT_LABELS = {
    "diff": "SIMOD 5.2.1, calendari fissi",
    "fuzz": "SIMOD 5.2.1, calendari FUZZY",
    "diff-loopfix": "diagnosi: fissi, ciclo riaperto",
    "fuzz-loopfix": "diagnosi: FUZZY, ciclo riaperto",
}


def _rows(results: dict, log: str) -> list[tuple[str, dict]]:
    """Le fonti di un log, nell'ordine della tabella: (etichetta, metriche)."""
    rows = [
        (VARIANT_LABELS.get(r["variant"], r["variant"]), r["metrics"])
        for r in results["simod"] if r["scenario"] == log
    ]
    rows.append(("scenario SIMOD del paper, in DeliR (B2)", results["paper_scenario_in_delir"][log]))
    rows.append(("paper, pubblicato", results["paper_published"][log]))
    rows.append(("gemello ingenuo (train)", results["naive_twin"][log]))
    return rows


def table(results: dict) -> str:
    lines = [
        "| Log | Scenario | " + " | ".join(LABELS[m] for m in COMPARED) + " |",
        "| --- | --- |" + " --- |" * len(COMPARED),
    ]
    for log in harness.REAL_LIFE:
        for label, metrics in _rows(results, log):
            lines.append(f"| {log} | {label} | " + " | ".join(_cell(metrics.get(m)) for m in COMPARED) + " |")
    return "\n".join(lines) + "\n"


def verdict_table(results: dict) -> str:
    """Ogni scenario SIMOD contro lo scenario del paper e contro il gemello ingenuo."""
    lines = [
        "| Log | Scenario | contro | " + " | ".join(LABELS[m] for m in COMPARED) + " |",
        "| --- | --- | --- |" + " --- |" * len(COMPARED),
    ]
    for r in results["simod"]:
        log = r["scenario"]
        for against, reference in (("paper in DeliR", results["paper_scenario_in_delir"][log]),
                                   ("ingenuo", results["naive_twin"][log])):
            cells = " | ".join(_verdict(r["metrics"][m], reference[m]) for m in COMPARED)
            lines.append(f"| {log} | {VARIANT_LABELS.get(r['variant'], r['variant'])} | {against} | {cells} |")
    return "\n".join(lines) + "\n"


def notes_table(results: dict) -> str:
    lines = ["| Log | Variante | Discovery (s) | Note d'import |", "| --- | --- | --- | --- |"]
    for r in results["simod"]:
        topics = Counter(f"{n['kind']}: {n['topic']}" for n in r["import_notes"])
        listed = "; ".join(f"{topic} ×{count}" for topic, count in sorted(topics.items()))
        lines.append(f"| {r['scenario']} | {r['variant']} | {r['discovery']['discovery_seconds']} | {listed or 'nessuna'} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=harness.DEFAULT_SEED)
    parser.add_argument("--replicas", type=int, default=harness.PAPER_REPLICAS)
    args = parser.parse_args(argv)
    results = evaluate_all(seed=args.seed, replicas=args.replicas)
    (HERE / "results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report = (
        f"# G3: SIMOD contro paper e gemello ingenuo (seed {args.seed}, {args.replicas} repliche)\n\n"
        "Media ± semiampiezza dell'IC 95%, distanze in ore sul log di test (più basso è meglio). "
        "\"pari\": lo scarto fra le medie è minore della somma degli intervalli.\n\n"
        + table(results) + "\n## Esito\n\n" + verdict_table(results)
        + "\n## Discovery e import\n\n" + notes_table(results)
    )
    (HERE / "results.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
