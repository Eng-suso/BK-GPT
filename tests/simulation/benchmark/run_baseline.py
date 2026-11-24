"""SIM-36: la baseline pubblica del gemello ingenuo "B sara' come A".

    uv run python scripts/fetch_datasets.py fetch bpic2012 bpic2013-incidents
    uv run python tests/simulation/benchmark/run_baseline.py [--seed N] [--replicas 10] [--out DIR] [bpic2012 ...]

Per ogni log: download verificato (``benchmark_datasets``), divisione in A e B a
meta' dei casi per inizio, previsione di B con il solo A, distanza dal B reale.
Le metriche sono quelle di B2 (``log_distance.py``, port di
``log-distance-measures`` 2.2), riassunte con media e intervallo t al 95% come
l'harness di B2: le due baseline si confrontano fra loro e con il paper.

Il gemello ingenuo e' A spostato in avanti sul periodo di B: la mediana degli
inizi dei casi di A cade sulla mediana di B (la mediana, perche' un caso isolato
anni prima non sposti tutto il resto). Lo spostamento e' di settimane intere e
l'inizio di ogni caso si sposta sull'ora locale del log: "B = A" ripete anche il
calendario di A (giorno della settimana e ora, ora legale compresa), altrimenti
CED misurerebbe la rotazione del calendario e non il processo. Gli eventi seguono
l'inizio del proprio caso in tempo assoluto: le durate restano quelle vere. Il prezzo e' uno scarto fino a 3,5
giorni fra le due mediane, che resta nelle distanze assolute (AED, CAR).

Ogni replica prende tanti casi quanti ne ha B, estratti con reinserimento dai
casi di A con il seed ``seed + replica``: l'intervallo dice quanto la baseline
dipende da quali casi di A si guardano.

Un evento senza inizio (le righe solo "complete" di BPIC 2012, i cambi di stato
di BPIC 2013) e' istantaneo: inizio = fine.

Scrive in ``--out`` (default ``tests/simulation/benchmark/sim36``):

- ``<log>.json``: le metriche del log, senza orari: con lo stesso seed il file e'
  identico bit per bit. Un log per file, cosi' i log si misurano uno alla volta;
- ``baseline.md``: i ``<log>.json`` dei log del benchmark in tabella, media ± intervallo.

I log non entrano nel repo: la licenza 4TU non lo permette. Un log che 4TU non
da' (manutenzione, rete) finisce nel file con il motivo e l'uscita e' 1: mai una
baseline inventata. Una misura gia' salvata non viene sostituita dal motivo.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

if __package__ in (None, ""):  # lanciato come script
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.eventlog.model import EventLog
from tests.simulation.benchmark.benchmark_datasets import DATASETS, DatasetUnavailable, fetch, load, manifest_entry
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


def _case_starts(events: list[Event]) -> dict[str, datetime]:
    return {case: min(e.start for e in group) for case, group in cases(events).items()}


def _median(instants: list[datetime]) -> datetime:
    return sorted(instants)[len(instants) // 2]


def split_in_half(events: list[Event]) -> tuple[list[Event], list[Event], datetime]:
    """Periodo A e periodo B: i casi divisi a meta' per inizio, e l'istante del taglio."""
    starts = _case_starts(events)
    if len(starts) < 2:
        raise ValueError("Servono almeno due casi per dividere il log in due periodi.")
    cutoff = _median(list(starts.values()))
    period_a = [e for e in events if starts[e.case_id] < cutoff]
    period_b = [e for e in events if starts[e.case_id] >= cutoff]
    return period_a, period_b, cutoff


@dataclass(frozen=True, slots=True)
class NaiveTwin:
    """Il gemello "B = A", preparato una volta: ogni replica estrae soltanto i casi."""

    by_case: dict[str, list[Event]]
    offsets: dict[str, timedelta]  # di quanto si sposta ogni caso di A
    cases_in_b: int

    @classmethod
    def of(cls, period_a: list[Event], period_b: list[Event], zone: ZoneInfo) -> NaiveTwin:
        by_case = cases(period_a)
        starts_a = {case: min(e.start for e in group) for case, group in by_case.items()}
        starts_b = _case_starts(period_b)
        gap = _median(list(starts_b.values())) - _median(list(starts_a.values()))
        shift = _WEEK * round(gap / _WEEK)
        # L'inizio del caso si sposta sull'orologio locale (con ZoneInfo la somma e' in ora
        # locale: le 9 restano le 9 oltre il cambio d'ora); i suoi eventi lo seguono in tempo
        # assoluto, cosi' le durate restano quelle vere.
        offsets = {case: (start.astimezone(zone) + shift).astimezone(UTC) - start for case, start in sorted(starts_a.items())}
        return cls(by_case, offsets, len(starts_b))

    def replica(self, rng: random.Random) -> list[Event]:
        """Una previsione di B: casi di A estratti con reinserimento, spostati su B."""
        drawn = rng.choices(list(self.offsets), k=self.cases_in_b)
        return [
            Event(f"{case}#{n}", e.activity, e.start + self.offsets[case], e.end + self.offsets[case])
            for n, case in enumerate(drawn)
            for e in self.by_case[case]
        ]


def measure(key: str, *, seed: int, replicas: int) -> dict:
    dataset = DATASETS[key]
    try:
        path = fetch(dataset)
    except DatasetUnavailable as exc:
        return {"scenario": key, "status": "unavailable", "reason": str(exc)}
    log, quality = load(path, dataset.mapping)
    period_a, period_b, cutoff = split_in_half(to_events(log))
    del log  # le repliche lavorano sugli eventi di A e B: il log intero non serve piu'
    twin = NaiveTwin.of(period_a, period_b, ZoneInfo(dataset.mapping.timestamps.timezone))

    measured = [distances(period_b, twin.replica(random.Random(seed + r))) for r in range(replicas)]
    entry = manifest_entry(dataset)
    return {
        "scenario": key,
        "status": "measured",
        "title": entry["title"],
        "source": entry["source"],
        "license": entry["license"],
        "twin": "naive: B = A",
        "rows_excluded": {issue.code: issue.count for issue in quality.issues if issue.excludes_rows},
        "cutoff": cutoff.isoformat(),
        "cases": {"A": len(twin.by_case), "B": twin.cases_in_b},
        "events": {"A": len(period_a), "B": len(period_b)},
        "seeds": [seed + r for r in range(replicas)],
        "metrics": {metric: summarize([m[metric] for m in measured]) for metric in METRICS},
    }


def _saved(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def replicas_error(replicas: int) -> str | None:
    if 2 <= replicas <= MAX_REPLICAS:
        return None
    return f"le repliche vanno da 2 a {MAX_REPLICAS}: serve un intervallo di confidenza"


def run(keys: list[str], out: Path, *, seed: int = DEFAULT_SEED, replicas: int = PAPER_REPLICAS) -> int:
    if error := replicas_error(replicas):
        raise ValueError(error)
    out.mkdir(parents=True, exist_ok=True)
    measured_all = True
    for key in keys:
        result = measure(key, seed=seed, replicas=replicas)
        target = out / f"{key}.json"
        if result["status"] != "measured":
            measured_all = False
            print(f"{key}: non misurato. {result['reason']}", file=sys.stderr)
            if (_saved(target) or {}).get("status") == "measured":
                continue  # la misura salvata resta: il motivo va solo a video
        report = {
            "benchmark": "SIM-36, tests/simulation/benchmark/run_baseline.py",
            "distances": "come B2: log-distance-measures 2.2 (port in log_distance.py); tempi in ore, ngram in [0, 1]",
            "seed": seed,
            "replicas": replicas,
            **result,
        }
        target.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_table(out)
    return 0 if measured_all else 1


def write_table(out: Path) -> None:
    """``baseline.md`` dai ``<log>.json`` dei log del benchmark nella cartella, misurati o no."""
    reports = [report for key in DATASETS if (report := _saved(out / f"{key}.json"))]
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
    if error := replicas_error(args.replicas):
        parser.error(error)
    code = run(args.datasets or list(DATASETS), args.out, seed=args.seed, replicas=args.replicas)
    print(f"Baseline scritta in {args.out}" + ("" if code == 0 else " (con log non disponibili)"))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
