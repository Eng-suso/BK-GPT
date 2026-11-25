"""PROTO-01: proprieta' dei log di sviluppo e verdetto di identificabilita' per metrica.

    uv run python scripts/fetch_datasets.py fetch bpic2012 bpic2013-incidents
    uv run python tests/simulation/benchmark/protocol_properties.py

Gira dentro ``protocol.selection_phase()``: gli holdout restano chiusi. Per ogni log
di sviluppo calcola dai dati (mai da un modello) casi, eventi, copertura di inizio
e risorsa, casi di test tagliati a destra e a sinistra, rapporto fra i ritmi degli
arrivi, e applica le regole di ``protocol.identifiability``. Nessun log escluso: un
log che 4TU non da' resta nella tabella con il motivo.

Scrive ``protocol/development.json`` (senza orari: stesso input, stesso file) e
``protocol/identifiability.md``, la tabella che PROTOCOL.md riporta.
"""

from __future__ import annotations

import csv
import gzip
import json
import sys
from dataclasses import asdict
from pathlib import Path

if __package__ in (None, ""):  # lanciato come script
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tests.simulation.benchmark import protocol
from tests.simulation.benchmark.benchmark_datasets import DATASETS, DatasetUnavailable, fetch, load
from tests.simulation.benchmark.log_distance import Event, events_from_rows
from tests.simulation.benchmark.run_baseline import split_in_half, to_events

OUT = protocol.BENCHMARK / "protocol"
METRICS = (
    ("cycle_time_w1", "W1 durata dei casi"),
    ("ngram", "NGD percorsi"),
    ("relative_event", "RED"),
    ("absolute_event", "AED"),
    ("circadian_event", "CED"),
    ("case_arrival", "CAR arrivi"),
    ("processing_time", "durate delle attivita'"),
    ("resources", "risorse"),
    ("waiting_causes", "cause delle attese"),
    ("true_parameters", "parametri veri"),
    ("counterfactual", "cosa succede se"),
)


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _coverage(rows: list[dict[str, str]]) -> tuple[list[bool], list[bool]]:
    return [bool(r.get("start_time")) for r in rows], [bool(r.get("resource")) for r in rows]


def _csv_periods(log: protocol.DevelopmentLog) -> tuple[list[Event], list[Event], list[bool], list[bool]]:
    if "{train,test}" in log.source:
        parts = [_csv_rows(protocol.ROOT / log.source.replace("{train,test}", part)) for part in ("train", "test")]
        rows = parts[0] + parts[1]
        train, test = events_from_rows(parts[0]), events_from_rows(parts[1])
    else:
        rows = _csv_rows(protocol.ROOT / log.source)
        train, test, _ = split_in_half(events_from_rows(rows))
    return train, test, *_coverage(rows)


def _public_periods(log: protocol.DevelopmentLog) -> tuple[list[Event], list[Event], list[bool], list[bool]]:
    dataset = DATASETS[log.key]
    event_log, _ = load(fetch(dataset), dataset.mapping)
    train, test, _ = split_in_half(to_events(event_log))
    return train, test, [e.start is not None for e in event_log.events], [bool(e.resource) for e in event_log.events]


def measure(log: protocol.DevelopmentLog) -> dict:
    row = {"log": log.key, "category": log.category, "source": log.source, "split": log.split}
    try:
        train, test, has_start, has_resource = (_public_periods if log.key in DATASETS else _csv_periods)(log)
    except DatasetUnavailable as exc:
        return {**row, "status": "unavailable", "reason": str(exc)}
    props = protocol.properties(train, test, has_start=has_start, has_resource=has_resource)
    verdicts = protocol.identifiability(props, synthetic=log.category == protocol.SYNTHETIC)
    return {
        **row,
        "properties": asdict(props),
        "metrics": {m: {"verdict": v, "reason": why} for m, (v, why) in verdicts.items()},
    }


def table(rows: list[dict]) -> str:
    head = "| Log | Categoria | Casi train / val / test | Inizio | Risorsa | Tagliati a destra / sinistra | " + " | ".join(
        label for _, label in METRICS
    ) + " |"
    lines = [head, "|" + " --- |" * (6 + len(METRICS))]
    reasons: dict[str, list[str]] = {}
    for row in rows:
        if row.get("status") == "unavailable":
            lines.append(f"| {row['log']} | {row['category']} | non disponibile: {row['reason']} |" + " |" * (3 + len(METRICS)))
            continue
        p = row["properties"]
        cells = []
        for metric, _ in METRICS:
            verdict = row["metrics"][metric]
            cells.append("sì" if verdict["verdict"] == protocol.IDENTIFIABLE else "**NV**")
            if verdict["reason"]:
                reasons.setdefault(verdict["reason"], []).append(f"{row['log']} {metric}")
        lines.append(
            f"| {row['log']} | {row['category']} | {p['cases_fit']} / {p['cases_validation']} / {p['cases_test']} | "
            f"{p['start_coverage']:.0%} | {p['resource_coverage']:.0%} | "
            f"{p['censored_right_test']:.0%} / {p['censored_left_test']:.0%} | " + " | ".join(cells) + " |"
        )
    lines += ["", "NV = NOT VALIDATED. Motivi:", ""]
    for reason, where in sorted(reasons.items()):
        logs = sorted({w.split(" ")[0] for w in where})
        lines.append(f"- {reason}: {', '.join(logs)}.")
    return "\n".join(lines) + "\n"


def main() -> int:
    with protocol.selection_phase():
        rows = [measure(log) for log in protocol.development_logs()]
    OUT.mkdir(exist_ok=True)
    (OUT / "development.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "identifiability.md").write_text(table(rows), encoding="utf-8")
    unavailable = [r["log"] for r in rows if r.get("status") == "unavailable"]
    print(f"{len(rows)} log di sviluppo, {len(unavailable)} non disponibili {unavailable or ''}")
    return 1 if unavailable else 0


if __name__ == "__main__":
    raise SystemExit(main())
