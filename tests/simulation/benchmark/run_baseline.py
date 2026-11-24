"""SIM-36: la baseline pubblica del gemello ingenuo "B sara' come A".

    uv run python scripts/fetch_datasets.py fetch bpic2012 bpic2013-incidents
    uv run python tests/simulation/benchmark/run_baseline.py [--seed N] [--replicas 10] [--out DIR] [bpic2012 ...]

Per ogni log: download verificato (``benchmark_datasets``), divisione in A e B a
meta' dei casi per inizio, previsione di B con il solo A, distanza dal B reale.
Le metriche sono quelle di B2 (``log_distance.py``, port di
``log-distance-measures`` 2.2), riassunte con media e intervallo t al 95% come
l'harness di B2: le due baseline si confrontano fra loro e con il paper.

Il gemello ingenuo e' A spostato in avanti, cosi' che il suo primo caso inizi
quando inizia il primo caso di B: e' cio' che fa B2 con un modello simulato,
che parte dal primo inizio del log di riferimento. Lo spostamento si arrotonda a
settimane intere: "B = A" ripete anche il calendario di A (giorno della
settimana e ora), altrimenti CED misurerebbe la rotazione e non il processo. Ogni replica prende tanti casi
quanti ne ha B, estratti con reinserimento dai casi di A con il seed
``seed + replica``: l'intervallo dice quanto la baseline dipende da quali casi
di A si guardano.

Un evento senza inizio (le righe solo "complete" di BPIC 2012, i cambi di stato
di BPIC 2013) e' istantaneo: inizio = fine.

Scrive in ``--out`` (default ``tests/simulation/benchmark/sim36``):

- ``<log>.json``: le metriche del log, senza orari: con lo stesso seed il file e'
  identico bit per bit. Un log per file, cosi' i log si misurano uno alla volta;
- ``baseline.md``: tutti i ``<log>.json`` della cartella in tabella, media ± intervallo.

I log non entrano nel repo: la licenza 4TU non lo permette. Un log che 4TU non
da' (manutenzione, rete) finisce nel file con il motivo e l'uscita e' 1: mai una
baseline inventata.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

if __package__ in (None, ""):  # lanciato come script
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.eventlog.model import EventLog
from tests.simulation.benchmark.benchmark_datasets import DATASETS, DatasetUnavailable, fetch, load
from tests.simulation.benchmark.eval_harness import DEFAULT_SEED, PAPER_REPLICAS, baseline_table, summarize
from tests.simulation.benchmark.log_distance import MAX_REPLICAS, METRICS, Event, cases, distances

DEFAULT_OUT = Path(__file__).resolve().with_name("sim36")
_WEEK = timedelta(weeks=1)


def to_events(log: EventLog) -> list[Event]:
    """Il log canonico nella forma delle distanze di B2, in UTC; senza inizio l'evento e' istantaneo."""
    return [
        Event(e.case_id, e.activity, (e.start or e.end).astimezone(UTC), e.end.astimezone(UTC))
        for e in log.events
    ]


def split_in_half(events: list[Event]) -> tuple[list[Event], list[Event], datetime]:
    """Periodo A e periodo B: i casi divisi a meta' per inizio, e l'istante del taglio."""
    starts = {case: min(e.start for e in group) for case, group in cases(events).items()}
    if len(starts) < 2:
        raise ValueError("Servono almeno due casi per dividere il log in due periodi.")
    cutoff = sorted(starts.values())[len(starts) // 2]
    period_a = [e for e in events if starts[e.case_id] < cutoff]
    period_b = [e for e in events if starts[e.case_id] >= cutoff]
    return period_a, period_b, cutoff


def naive_replica(period_a: list[Event], period_b: list[Event], rng: random.Random) -> list[Event]:
    """Una previsione di B: casi di A estratti con reinserimento, spostati all'inizio di B a settimane intere."""
    by_case = cases(period_a)
    shift = _WEEK * round((min(e.start for e in period_b) - min(e.start for e in period_a)) / _WEEK)
    drawn = rng.choices(sorted(by_case), k=len(cases(period_b)))
    return [
        Event(f"{case}#{n}", e.activity, e.start + shift, e.end + shift)
        for n, case in enumerate(drawn)
        for e in by_case[case]
    ]


def measure(key: str, *, seed: int, replicas: int) -> dict:
    dataset = DATASETS[key]
    try:
        path = fetch(dataset)
    except DatasetUnavailable as exc:
        return {"scenario": key, "status": "unavailable", "reason": str(exc)}
    period_a, period_b, cutoff = split_in_half(to_events(load(path, dataset.mapping)))

    measured = [
        distances(period_b, naive_replica(period_a, period_b, random.Random(seed + r)))
        for r in range(replicas)
    ]
    return {
        "scenario": key,
        "status": "measured",
        "title": dataset.title,
        "doi": dataset.doi,
        "license": dataset.license,
        "twin": "naive: B = A",
        "cutoff": cutoff.isoformat(),
        "cases": {"A": len(cases(period_a)), "B": len(cases(period_b))},
        "events": {"A": len(period_a), "B": len(period_b)},
        "seeds": [seed + r for r in range(replicas)],
        "metrics": {metric: summarize([m[metric] for m in measured]) for metric in METRICS},
    }


def run(keys: list[str], out: Path, *, seed: int = DEFAULT_SEED, replicas: int = PAPER_REPLICAS) -> int:
    out.mkdir(parents=True, exist_ok=True)
    results = [measure(key, seed=seed, replicas=replicas) for key in keys]
    for result in results:
        report = {
            "benchmark": "SIM-36, tests/simulation/benchmark/run_baseline.py",
            "metrics": "come B2: log-distance-measures 2.2 (port in log_distance.py); tempi in ore, ngram in [0, 1]",
            "seed": seed,
            "replicas": replicas,
            **result,
        }
        text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
        (out / f"{result['scenario']}.json").write_text(text, encoding="utf-8")
    write_table(out)
    return 0 if all(r["status"] == "measured" for r in results) else 1


def write_table(out: Path) -> None:
    """``baseline.md`` da tutti i ``<log>.json`` della cartella, misurati o no."""
    reports = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(out.glob("*.json"))]
    measured = [r for r in reports if r["status"] == "measured"]
    lines = ['# Baseline SIM-36, gemello ingenuo "B = A"\n']
    if measured:
        settings = sorted({(r["seed"], r["replicas"]) for r in measured})
        lines.append("Seed e repliche: " + ", ".join(f"{s} × {n}" for s, n in settings) + ".\n")
        lines.append(baseline_table(measured))
    lines += [f"- {r['scenario']}: non misurato. {r['reason']}" for r in reports if r["status"] != "measured"]
    (out / "baseline.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("datasets", nargs="*", choices=list(DATASETS), help="default: tutti")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--replicas", type=int, default=PAPER_REPLICAS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    if not 2 <= args.replicas <= MAX_REPLICAS:
        parser.error(f"--replicas va da 2 a {MAX_REPLICAS}: serve un intervallo di confidenza")
    code = run(args.datasets or list(DATASETS), args.out, seed=args.seed, replicas=args.replicas)
    print(f"Baseline scritta in {args.out}" + ("" if code == 0 else " (con log non disponibili)"))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
