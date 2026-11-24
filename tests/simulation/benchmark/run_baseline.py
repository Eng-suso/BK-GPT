"""SIM-36 e SIM-36b: la baseline del gemello ingenuo "B sara' come A".

    uv run python scripts/fetch_datasets.py fetch bpic2012 bpic2013-incidents
    uv run python tests/simulation/benchmark/run_baseline.py [--seed N] [--replicas 10] [--out DIR] [log ...]

Due famiglie di log:

- i 3 log reali del paper con il loro train e test (SIM-36b, il banco principale
  A -> B): A e' il train, B il test, gli stessi file con cui B2 misura lo scenario
  SIMOD del paper. Stanno nel repo (CC BY 4.0), niente rete;
- i log pubblici BPIC (SIM-36): download verificato (``benchmark_datasets``) e
  divisione in A e B a meta' dei casi per inizio. BPIC 2013 incidents resta
  misurato ma marcato come non adatto al confronto A -> B.

Per ogni log: previsione di B con il solo A, distanza dal B reale.
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
- ``baseline.md``: i ``<log>.json`` dei log del benchmark in tabella, media ± intervallo,
  e sui log train/test "B = A" contro lo scenario SIMOD del paper misurato da B2
  (``--b2``, default ``b2/baseline.json``), metrica per metrica.

I log BPIC non entrano nel repo: la licenza 4TU non lo permette. Un log che 4TU non
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
from tests.simulation.benchmark.eval_harness import (
    DEFAULT_OUT as B2_OUT,
    DEFAULT_SEED,
    INPUTS,
    PAPER_REPLICAS,
    METRIC_LABELS,
    REAL_LIFE,
    ROOT,
    baseline_table,
    cell,
    summarize,
    within_intervals,
)
from tests.simulation.benchmark.log_distance import MAX_REPLICAS, METRICS, Event, cases, distances, read_csv_log

DEFAULT_OUT = Path(__file__).resolve().with_name("sim36")
DEFAULT_B2 = B2_OUT / "baseline.json"
TRAIN_TEST_DIR = INPUTS / "real-life"
_SCRIPT = "tests/simulation/benchmark/run_baseline.py"
_TRAIN_TEST_MANIFEST_ID = "extraneous-delays-inputs"
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


# Una fonte da' periodo A, periodo B, fuso in cui spostare il calendario e la descrizione del log.
Periods = tuple[list[Event], list[Event], ZoneInfo, dict]


def _train_test(log: str) -> Periods:
    """A = train, B = test: i file del paper con cui B2 misura il suo scenario SIMOD.

    I CSV del paper non hanno fuso: l'orologio del log e' quello scritto, e lo
    spostamento di settimane intere in UTC lo conserva.
    """
    files = {period: TRAIN_TEST_DIR / f"{log}_{part}.csv.gz" for period, part in (("A", "train"), ("B", "test"))}
    entry = manifest_entry(_TRAIN_TEST_MANIFEST_ID)
    return read_csv_log(files["A"]), read_csv_log(files["B"]), ZoneInfo("UTC"), {
        "benchmark": f"SIM-36b, {_SCRIPT}",
        "title": f"{log}, train e test del paper Extraneous Activity Delays",
        "source": entry["source"],
        "license": entry["license"],
        "split": "train / test del paper",
        "logs": {period: path.relative_to(ROOT).as_posix() for period, path in files.items()},
    }


def _half_split(key: str) -> Periods:
    """A e B a meta' dei casi di un log BPIC scaricato; ``DatasetUnavailable`` se 4TU non lo da'."""
    dataset = DATASETS[key]
    log, quality = load(fetch(dataset), dataset.mapping)
    period_a, period_b, cutoff = split_in_half(to_events(log))
    entry = manifest_entry(dataset.manifest_id)
    about = {
        "benchmark": f"SIM-36, {_SCRIPT}",
        "title": entry["title"],
        "source": entry["source"],
        "license": entry["license"],
        "split": "meta' dei casi per inizio",
        "rows_excluded": {issue.code: issue.count for issue in quality.issues if issue.excludes_rows},
        "cutoff": cutoff.isoformat(),
    }
    if dataset.unsuitable_for_a_to_b:
        about["unsuitable_for_a_to_b"] = dataset.unsuitable_for_a_to_b
    return period_a, period_b, ZoneInfo(dataset.mapping.timestamps.timezone), about


SOURCES = {**dict.fromkeys(REAL_LIFE, _train_test), **dict.fromkeys(DATASETS, _half_split)}


def measure(key: str, *, seed: int, replicas: int) -> dict:
    try:
        period_a, period_b, zone, about = SOURCES[key](key)
    except DatasetUnavailable as exc:
        return {"scenario": key, "status": "unavailable", "reason": str(exc)}
    twin = NaiveTwin.of(period_a, period_b, zone)

    measured = [distances(period_b, twin.replica(random.Random(seed + r))) for r in range(replicas)]
    return {
        "scenario": key,
        "status": "measured",
        **about,
        "twin": "naive: B = A",
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


def run(
    keys: list[str], out: Path, *, seed: int = DEFAULT_SEED, replicas: int = PAPER_REPLICAS, b2: Path | None = DEFAULT_B2
) -> int:
    """``b2``: il ``baseline.json`` di B2 con cui confrontare i log train/test; None per non confrontare."""
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
            "benchmark": f"SIM-36, {_SCRIPT}",  # quello del log, se misurato
            "distances": "come B2: log-distance-measures 2.2 (port in log_distance.py); tempi in ore, ngram in [0, 1]",
            "seed": seed,
            "replicas": replicas,
            **result,
        }
        target.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_table(out, b2)
    return 0 if measured_all else 1


def verdict(naive: dict, model: dict) -> str:
    """Chi prevede meglio B: vince chi ha la distanza minore, con intervalli al 95% separati."""
    if within_intervals(naive, model):
        return "pari"
    return "B = A" if naive["mean"] < model["mean"] else "SIMOD"


def simod_comparison(reports: list[dict], b2: dict | None) -> list[str]:
    """"B = A" contro lo scenario SIMOD del paper di B2, log per log, solo con lo stesso seed e le stesse repliche."""
    if b2 is None:
        return ["Confronto con B2 non disponibile: nessun `baseline.json` di B2."]
    scenarios = {s["scenario"]: s for s in b2["scenarios"]}
    rows, notes = [], []
    for report in reports:
        log = report["scenario"]
        if log not in scenarios:
            notes.append(f"- {log}: confronto con B2 non fatto, B2 non ha misurato questo log.")
            continue
        if (report["seed"], report["replicas"]) != (b2["seed"], b2["replicas"]):
            notes.append(f"- {log}: confronto con B2 non fatto, B2 ha seed {b2['seed']} × {b2['replicas']}, "
                         f"il log {report['seed']} × {report['replicas']}.")
            continue
        model = scenarios[log]["metrics"]
        for metric in METRICS:
            naive = report["metrics"][metric]
            rows.append(f"| {log} | {METRIC_LABELS[metric]} | {cell(naive)} | {cell(model[metric])} "
                        f"| {verdict(naive, model[metric])} |")
    if not rows:
        return notes
    header = ["| Log | Metrica | B = A (train) | SIMOD del paper (B2) | Migliore |", "| --- | --- | --- | --- | --- |"]
    return header + rows + ([""] + notes if notes else [])


def write_table(out: Path, b2: Path | None = DEFAULT_B2) -> None:
    """``baseline.md`` dai ``<log>.json`` dei log del benchmark nella cartella, misurati o no."""
    reports = [report for key in SOURCES if (report := _saved(out / f"{key}.json"))]
    measured = [r for r in reports if r["status"] == "measured"]
    train_test = [r for r in measured if r["scenario"] in REAL_LIFE]
    halves = [r for r in measured if r["scenario"] not in REAL_LIFE]
    lines = ['# Baseline SIM-36 e SIM-36b, gemello ingenuo "B = A"\n']
    if measured:
        settings = sorted({(r["seed"], r["replicas"]) for r in measured})
        lines.append("Seed e repliche: " + ", ".join(f"{s} × {n}" for s, n in settings) + ".\n")
    if train_test:
        lines += [
            "## Log train/test del paper (SIM-36b): A = train, B = test\n",
            baseline_table(train_test),
            '## "B = A" contro lo scenario SIMOD del paper (B2)\n',
            "Distanza dal test, piu' bassa e' meglio. Migliore: chi ha la media minore con intervalli "
            "al 95% che non si sovrappongono; altrimenti pari.\n",
            *simod_comparison(train_test, _saved(b2) if b2 else None),
            "",
        ]
    if halves:
        lines += ["## Log BPIC divisi a meta' dei casi (SIM-36)\n", baseline_table(halves)]
    lines += [f"- {r['scenario']}: non adatto al confronto A → B, {r['unsuitable_for_a_to_b']}."
              for r in measured if r.get("unsuitable_for_a_to_b")]
    lines += [f"- {r['scenario']}: non misurato. {r['reason']}" for r in reports if r["status"] != "measured"]
    (out / "baseline.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("datasets", nargs="*", choices=list(SOURCES), help="default: tutti")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--replicas", type=int, default=PAPER_REPLICAS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--b2", type=Path, default=DEFAULT_B2, help="baseline.json di B2 per il confronto con SIMOD")
    args = parser.parse_args(argv)
    if error := replicas_error(args.replicas):
        parser.error(error)
    code = run(args.datasets or list(SOURCES), args.out, seed=args.seed, replicas=args.replicas, b2=args.b2)
    print(f"Baseline scritta in {args.out}" + ("" if code == 0 else " (con log non disponibili)"))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
