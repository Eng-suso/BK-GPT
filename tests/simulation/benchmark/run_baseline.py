"""SIM-36: la baseline del benchmark, misurata con il gemello ingenuo "B sara' come A".

    python tests/simulation/benchmark/run_baseline.py [--out baseline.json] [bpic2012 ...]

Per ogni log: download verificato, divisione in A e B a meta' dei casi per
inizio, obiettivo di servizio all'80% dei casi di A, metriche della previsione
contro il B reale. Il tempo di configurazione umana non si misura da qui: resta
``null`` finche' un consulente non lo cronometra.

Un log che 4TU non da' (manutenzione, rete) finisce nel file con il motivo e
l'uscita e' 1: mai una baseline inventata.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

if __package__ in (None, ""):  # lanciato come script
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tests.simulation.benchmark.benchmark_datasets import DATASETS, DatasetUnavailable, fetch, load
from tests.simulation.benchmark.benchmark_metrics import (
    compare,
    default_sla_target,
    median_case_start,
    naive_prediction,
    split_by_case_start,
)

DEFAULT_OUT = Path(__file__).with_name("baseline.json")


def measure(key: str, *, client: httpx.Client | None = None) -> dict:
    dataset = DATASETS[key]
    try:
        path = fetch(dataset, client=client)
    except DatasetUnavailable as exc:
        return {"dataset": key, "status": "unavailable", "reason": str(exc)}
    log = load(path)
    cutoff = median_case_start(log)
    period_a, period_b = split_by_case_start(log, cutoff)

    started = time.perf_counter()
    prediction = naive_prediction(period_a)
    calibration_seconds = time.perf_counter() - started
    target = default_sla_target(period_a)
    metrics = compare(prediction, period_b, sla_target_seconds=target)

    return {
        "dataset": key,
        "status": "measured",
        "title": dataset.title,
        "doi": dataset.doi,
        "license": dataset.license,
        "twin": "naive: B = A",
        "cutoff": cutoff.isoformat(),
        "cases": {"A": len(period_a.cases()), "B": len(period_b.cases())},
        "metrics": metrics.as_dict(),
        "efficiency": {
            "calibration_seconds": round(calibration_seconds, 3),
            # Il gemello ingenuo non simula: nessun run del motore.
            "simulation_seconds": 0.0,
            "human_configuration_minutes": None,
        },
    }


def run(keys: list[str], out: Path, *, client: httpx.Client | None = None) -> int:
    results = [measure(key, client=client) for key in keys]
    report = {"benchmark": "DeliR Simulation Benchmark", "version": 1, "measured_at": datetime.now(UTC).isoformat(), "results": results}
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0 if all(r["status"] == "measured" for r in results) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("datasets", nargs="*", default=list(DATASETS), choices=list(DATASETS))
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    code = run(args.datasets, args.out)
    print(f"Baseline scritta in {args.out}" + ("" if code == 0 else " (con log non disponibili)"))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
