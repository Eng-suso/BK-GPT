"""B3.1: verdetti delle schede degli arrivi dai risultati di ``b3_1/run.py``.

    uv run python tests/simulation/benchmark/b3_1/report.py

Le schede sono in ``docs/vpt/LOG.md``, scritte prima della misura; le regole quelle di
PROTOCOL.md §7 applicate da ``g3b/report.py``, con CAR e AED co-primarie: ognuna vince sulla
maggioranza dei log dove e' identificabile e non perde su nessuno, le guardie (W1, NGD, RED,
CED) non perdono su piu' di un log, il costo e' al massimo il doppio di ``simod_extr``.
VAL-01, lettura dichiarata nella scheda: lo scenario simulato e' quello della base, quindi
la condizione e' "VAL-01 uguale a quello di ``simod_extr``" (lo stesso scenario in cache).
Scrive ``results.md`` e ``verdicts.json``.

Due verdetti per scheda. "Regola delle schede": quella scritta nelle schede, contro
``simod_extr`` e "B = A", CAR e AED co-primarie. "Meta del 2026-11-27" (decisione di Sohayb,
LOG.md): solo contro ``simod_extr``, CAR primaria con la regola del §7, AED non perde su nessun
log, le altre guardie come sopra, e si contano solo i log dove la base e' misurata.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

if __package__ in (None, ""):  # lanciato come script
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from tests.simulation.benchmark import protocol
from tests.simulation.benchmark.b3_1.run import CONFIGS, RESULTS
from tests.simulation.benchmark.g3b import report as g3b
from tests.simulation.benchmark.g3b.run import PHASES
from tests.simulation.benchmark.log_distance import METRICS

HERE = Path(__file__).resolve().parent
PRIMARIES = ("case_arrival", "absolute_event")
BASES = ("simod_extr", "naive")


@dataclass(frozen=True, slots=True)
class Card:
    name: str
    candidate: str


CARDS = (
    Card("B3.1-C1 arrivi di A rigiocati", "simod_extr_replay"),
    Card("B3.1-C2 giorni dell'input ricampionati", "simod_extr_days"),
    Card("B3.1-C3 giorni delle ultime 4 settimane", "simod_extr_recent"),
)


def load_results() -> dict[tuple[str, str, str], dict]:
    return {
        (path.parts[-3], path.parts[-2], path.stem): json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(RESULTS.glob("*/*/*.json"))
    }


def verdict(card: Card, phase: str, results: dict, logs: list[str]) -> dict:
    """GO se valgono le schede di G3b con primaria CAR e con primaria AED, e VAL-01 e' quello della base."""
    reasons: list[str] = []
    per_primary = {}
    for primary in PRIMARIES:
        # VAL-01 si controlla sotto, contro la base: qui "per costruzione" lo salta.
        one = g3b.verdict(g3b.Card(card.name, card.candidate, BASES, primary, "per costruzione"), phase, results, logs)
        per_primary[g3b.LABELS[primary]] = one
        reasons += [r for r in one["reasons"] if r not in reasons]
    found = {one["verdict"] for one in per_primary.values()}
    outcome = next((v for v in ("INCOMPLETO", "NOT VALIDATED", "NO-GO") if v in found), "GO")
    differs = _val01_differs(card, phase, results, logs)
    if differs:
        reasons.append(f"VAL-01 diverso da quello della base su {', '.join(differs)}")
        outcome = "NO-GO" if outcome == "GO" else outcome
    return {"verdict": outcome, "reasons": reasons, "primaries": per_primary}


def verdict_meta(card: Card, phase: str, results: dict, logs: list[str]) -> dict:
    """La meta del 2026-11-27: contro ``simod_extr``, CAR vince e AED non perde su nessun log."""
    base = BASES[0]
    unmeasured = [log for log in logs if (b := results.get((log, phase, base))) and not g3b.measured(b)]
    compared = [log for log in logs if log not in unmeasured]
    one = g3b.verdict(g3b.Card(card.name, card.candidate, (base,), "case_arrival", "per costruzione"), phase, results, compared)
    reasons = list(one["reasons"])
    aed = one.get("bases", {}).get(base, {}).get("guard_losses", {}).get(g3b.LABELS["absolute_event"], [])
    if len(aed) == 1:  # la guardia ne tollera uno, la meta nessuno
        reasons.append(f"contro {base}: AED perde su {aed[0]}")
    outcome = one["verdict"] if one["verdict"] != "GO" or not aed else "NO-GO"
    differs = _val01_differs(card, phase, results, compared)
    if differs:
        reasons.append(f"VAL-01 diverso da quello della base su {', '.join(differs)}")
        outcome = "NO-GO" if outcome == "GO" else outcome
    if unmeasured:
        reasons.append(f"esclusi, base non misurata: {', '.join(unmeasured)}")
    return {"verdict": outcome, "reasons": reasons, "primaries": {g3b.LABELS["case_arrival"]: one}}


def _val01_differs(card: Card, phase: str, results: dict, logs: list[str]) -> list[str]:
    return [
        log for log in logs
        if (c := results.get((log, phase, card.candidate))) and (b := results.get((log, phase, "simod_extr")))
        and c.get("cost", {}).get("val01") != b.get("cost", {}).get("val01")
    ]


def report(results: dict) -> tuple[str, dict]:
    logs = [log.key for log in protocol.development_logs() if any(k[0] == log.key for k in results)]
    configs = [c for c in CONFIGS if any(k[2] == c for k in results)]
    lines = [
        "# B3.1: arrivi non stazionari",
        "",
        "Generato da `tests/simulation/benchmark/b3_1/report.py` dai file in `results/`. Schede in",
        "`docs/vpt/LOG.md`. Distanze di B2 (tempi in ore, NGD in [0, 1]): media ± semiampiezza IC 95%",
        "su 10 repliche; (NV) = NOT VALIDATED (PROTOCOL.md §4). Più basso è meglio.",
        "",
        "## Verdetti",
        "",
        "| Scheda | Fase | Regola | Verdetto | Motivi |",
        "| --- | --- | --- | --- | --- |",
    ]
    verdicts = {}
    measured_cards = [c for c in CARDS if c.candidate in configs]
    for card in measured_cards:
        for phase in PHASES:
            if not any(k[1] == phase and k[2] == card.candidate for k in results):
                continue
            for rule, judge in RULES.items():
                v = judge(card, phase, results, logs)
                verdicts[f"{card.name} / {phase} / {rule}"] = v
                lines.append(f"| {card.name} | {phase} | {rule} | **{v['verdict']}** | {'; '.join(v['reasons']) or '—'} |")
    lines += ["", "## Primarie contro ogni base", "", "Vince / pari / perde sui log dove la primaria è identificabile.", "",
              "| Scheda | Fase | Primaria | Base | Vince / pari / perde | Perde su |", "| --- | --- | --- | --- | --- | --- |"]
    for key, v in verdicts.items():
        name, phase, rule = key.split(" / ")
        if rule != RULE_CARDS:
            continue
        for label, one in v["primaries"].items():
            for base, b in one.get("bases", {}).items():
                lines.append(f"| {name} | {phase} | {label} | {base} | {b['wins']} / {b['ties']} / {len(b['losses'])} | "
                             f"{', '.join(b['losses']) or '—'} |")
    for phase in PHASES:
        lines += ["", f"## Metriche, fase {phase}", ""]
        for log in logs:
            rows = [results[(log, phase, c)] for c in configs if (log, phase, c) in results]
            if not rows:
                continue
            lines += [f"### {log}", "", "| Configurazione | " + " | ".join(g3b.LABELS.values()) + " | Costo (tempo, picco, replica più lenta) |",
                      "|" + " --- |" * (len(g3b.LABELS) + 2)]
            lines += [f"| {r['label']} | " + " | ".join(g3b._cell(r, m) for m in METRICS) + f" | {g3b._cost_cell(r)} |" for r in rows]
            lines.append("")
    return "\n".join(lines).rstrip() + "\n", verdicts


RULE_CARDS = "regola delle schede"
RULES = {RULE_CARDS: verdict, "meta del 2026-11-27": verdict_meta}


def main() -> int:
    text, verdicts = report(load_results())
    (HERE / "results.md").write_text(text, encoding="utf-8")
    (HERE / "verdicts.json").write_text(json.dumps(verdicts, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(text.split("## Metriche")[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
