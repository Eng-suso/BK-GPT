"""G3b, diagnosi: il simulatore della ricerca e' quello del prodotto?

    uv run python tests/simulation/benchmark/g3b/engine_check.py [--scenario BPIC_2012_W_extr]

G3b simula gli scenari SIMOD con Prosimos 2.1.0 chiamato direttamente nel venv di
ricerca (serve per gli arrivi AT-KDE e per l'ablazione dei calendari, che il runner del
prodotto non accetta). G3 ha simulato gli stessi scenari sul percorso del prodotto
(import nell'IR, coda, runner). Qui uno scenario di G3 si simula nel modo di G3b con lo
stesso log di test, lo stesso seed e le stesse repliche, e si confrontano le sei
distanze con quelle di ``g3/results.json`` con la regola "pari" di B2
(``within_intervals``). Scrive ``engine_check.json``.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

if __package__ in (None, ""):  # lanciato come script
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from tests.simulation.benchmark import protocol
from tests.simulation.benchmark.eval_harness import DEFAULT_SEED, INPUTS, PAPER_REPLICAS, summarize, within_intervals
from tests.simulation.benchmark.g3b.run import prosimos, read_simulated, tool_args
from tests.simulation.benchmark.log_distance import METRICS, distances, read_csv_log

HERE = Path(__file__).resolve().parent
G3 = HERE.parent / "g3"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default="BPIC_2012_W_extr")
    args = parser.parse_args(argv)
    log, variant = args.scenario.rsplit("_", 1)
    folder = G3 / "discovered" / args.scenario
    product = next(
        r for r in json.loads((G3 / "results.json").read_text(encoding="utf-8"))["simod"]
        if r["scenario"] == log and r["variant"] == variant
    )
    with protocol.selection_phase(), tempfile.TemporaryDirectory() as work:
        test = read_csv_log(INPUTS / "real-life" / f"{log}_test.csv.gz")
        out = Path(work)
        # Lo stesso comando con cui run.py simula gli scenari SIMOD.
        prosimos(folder / f"{log}.bpmn", folder / f"{log}.json",
                 tool_args(product["cases"], product["start"], DEFAULT_SEED, PAPER_REPLICAS, out), out, PAPER_REPLICAS)
        direct = [distances(test, read_simulated(out / f"sim_{r}.csv")) for r in range(PAPER_REPLICAS)]
    rows = {}
    for metric in METRICS:
        ours = summarize([d[metric] for d in direct])
        theirs = product["metrics"][metric]
        rows[metric] = {
            "g3b_direct": {"mean": ours["mean"], "ci95": ours["ci95"]},
            "g3_product_path": {"mean": theirs["mean"], "ci95": theirs["ci95"]},
            "same": within_intervals(ours, theirs),
            "identical_replicas": ours["replicas"] == theirs["replicas"],
        }
    report = {"scenario": args.scenario, "seed": DEFAULT_SEED, "replicas": PAPER_REPLICAS, "cases": product["cases"],
              "start": product["start"], "metrics": rows}
    (HERE / "engine_check.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for metric, row in rows.items():
        print(f"{metric}: diretto {row['g3b_direct']['mean']:.3f} ± {row['g3b_direct']['ci95']:.3f}, "
              f"prodotto {row['g3_product_path']['mean']:.3f} ± {row['g3_product_path']['ci95']:.3f}, pari: {row['same']}, identiche: {row['identical_replicas']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
