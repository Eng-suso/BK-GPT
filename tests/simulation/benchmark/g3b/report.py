"""G3b: tabelle e verdetti delle schede di go/no-go dai risultati di ``run.py``.

    uv run python tests/simulation/benchmark/g3b/report.py

Legge ``results/<log>/<fase>/<configurazione>.json`` e scrive ``results.md``
(metriche per log, costi, verdetto di ogni scheda per fase) e ``verdicts.json``.
Le schede sono quelle scritte in ``docs/vpt/LOG.md`` prima della misura; le regole
quelle di PROTOCOL.md §7:

- per ogni base, la primaria vince (IC 95% separati) sulla maggioranza dei log dove e'
  identificabile e non perde su nessuno;
- nessuna guardia perde su piu' di un log (ogni guardia, nei log dove e' identificabile);
- tempo (discovery + simulazione) e picco di memoria del candidato al massimo il doppio
  della base. Contro "B = A" questa regola non si applica: "B = A" non ha discovery e
  ogni modello costerebbe infinite volte di piu' (lettura da confermare con Sohayb);
- il modello supera VAL-01;
- fallito, fuori budget o non applicabile conta come sconfitta su tutte le metriche, per
  il candidato come per la base; un candidato mancante perde; una base mai lanciata rende
  il confronto "incompleto" (niente GO).
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

if __package__ in (None, ""):  # lanciato come script
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from tests.simulation.benchmark import protocol
from tests.simulation.benchmark.log_distance import METRICS

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
PHASES = ("validation", "test")
LABELS = {
    "cycle_time_w1": "W1",
    "ngram": "NGD",
    "relative_event": "RED",
    "absolute_event": "AED",
    "circadian_event": "CED",
    "case_arrival": "CAR",
}


@dataclass(frozen=True, slots=True)
class Card:
    component: str
    candidate: str
    bases: tuple[str, ...]
    primary: str
    val01: str  # "scenario": require_sound sullo scenario; "per costruzione"; "non verificabile"


CARDS = (
    Card("Arrivi (AT-KDE)", "simod_extr_atkde", ("naive", "simod_extr"), "case_arrival", "scenario"),
    Card("Attese (ritardi estranei)", "simod_extr", ("naive", "simod"), "relative_event", "scenario"),
    Card("Calendari delle risorse", "simod_extr", ("naive", "simod_extr_247"), "circadian_event", "scenario"),
    Card("Control flow e risorse condizionali", "prosit", ("naive", "simod_extr", "prosit_norules"), "ngram", "per costruzione"),
    Card("Approccio intero: ProSiT", "prosit", ("naive", "simod_extr"), "cycle_time_w1", "per costruzione"),
    Card("Approccio intero: AgentSimulator", "agentsim", ("naive", "simod_extr"), "cycle_time_w1", "non verificabile"),
)


def load_results() -> dict[tuple[str, str, str], dict]:
    found = {}
    for path in sorted(RESULTS.glob("*/*/*.json")):
        found[(path.parts[-3], path.parts[-2], path.stem)] = json.loads(path.read_text(encoding="utf-8"))
    return found


def compare(candidate: dict | None, base: dict | None, metric: str) -> str:
    """vince, perde, pari; ``incompleto`` se la base non e' stata lanciata.

    Fallito, fuori budget o non applicabile e' una sconfitta su tutte le metriche (§6), per
    il candidato come per la base; due sconfitte sono pari. Un candidato mancante perde.
    """
    if base is None:
        return "incompleto"
    base_ok = base.get("status") == "measured"
    candidate_ok = candidate is not None and candidate.get("status") == "measured"
    if not (base_ok and candidate_ok):
        return "pari" if base_ok == candidate_ok else ("perde" if base_ok else "vince")
    c, b = candidate["metrics"][metric], base["metrics"][metric]
    if c["mean"] + c["ci95"] < b["mean"] - b["ci95"]:
        return "vince"
    if b["mean"] + b["ci95"] < c["mean"] - c["ci95"]:
        return "perde"
    return "pari"


def identifiable(result: dict | None, metric: str) -> bool:
    return bool(result) and result["identifiability"].get(metric) == protocol.IDENTIFIABLE


def cost(result: dict | None) -> tuple[float, float] | None:
    """Tempo totale (discovery + simulazione) e picco di memoria in MB."""
    if not result or "cost" not in result:
        return None
    c = result["cost"]
    seconds = c.get("discovery_seconds", c.get("seconds", 0.0)) + sum(c.get("simulation_seconds", []))
    peak = max(c.get(k, 0.0) for k in ("peak_mb", "discovery_peak_mb", "simulation_peak_mb"))
    return seconds, peak


def verdict(card: Card, phase: str, results: dict, logs: list[str]) -> dict:
    rows = {log: results.get((log, phase, card.candidate)) for log in logs}
    # Identificabilita' dal periodo, uguale per tutte le configurazioni: si prende la prima che c'e'.
    reference = {log: next((r for (l, p, _), r in results.items() if l == log and p == phase), None) for log in logs}
    usable = [log for log in logs if identifiable(reference[log], card.primary)]
    reasons: list[str] = []
    per_base = {}
    if len(usable) < 2:
        return {"verdict": "NOT VALIDATED", "reasons": [f"{LABELS[card.primary]} identificabile in {len(usable)} log"], "bases": {}}
    complete = True
    for base in card.bases:
        outcome = {log: compare(rows[log], results.get((log, phase, base)), card.primary) for log in usable}
        wins = sum(v == "vince" for v in outcome.values())
        losses = [log for log, v in outcome.items() if v == "perde"]
        missing = [log for log, v in outcome.items() if v == "incompleto"]
        guards = {}
        for metric in METRICS:
            if metric == card.primary:
                continue
            lost = [
                log for log in logs
                if identifiable(reference[log], metric) and compare(rows[log], results.get((log, phase, base)), metric) == "perde"
            ]
            guards[LABELS[metric]] = lost
        costly = []
        if base != "naive":
            for log in logs:
                mine, theirs = cost(rows[log]), cost(results.get((log, phase, base)))
                if mine and theirs and (mine[0] > 2 * theirs[0] or mine[1] > 2 * theirs[1]):
                    costly.append(log)
        per_base[base] = {
            "wins": wins, "ties": sum(v == "pari" for v in outcome.values()), "logs": len(usable), "losses": losses, "missing": missing,
            "guard_losses": {m: v for m, v in guards.items() if v}, "costlier_than_double": costly,
        }
        if missing:
            complete = False
            reasons.append(f"contro {base}: base mancante su {', '.join(missing)}")
        if wins <= len(usable) / 2:
            reasons.append(f"contro {base}: {LABELS[card.primary]} vince su {wins}/{len(usable)} log")
        if losses:
            reasons.append(f"contro {base}: {LABELS[card.primary]} perde su {_logs(losses)}")
        for metric, lost in guards.items():
            if len(lost) > 1:
                reasons.append(f"contro {base}: guardia {metric} perde su {len(lost)} log")
        if costly:
            reasons.append(f"contro {base}: tempo o memoria oltre il doppio su {len(costly)} log")
    budget = [log for log, r in rows.items() if r is None or r.get("status") != "measured"]
    if budget:
        reasons.append(f"candidato non misurato (fallito, fuori budget o non applicabile) su {_logs(budget)}")
    if card.val01 == "non verificabile":
        reasons.append("VAL-01 non verificabile: nessun modello di processo")
    elif card.val01 == "scenario":
        failing = [log for log, r in rows.items() if r and r.get("cost", {}).get("val01", "supera") != "supera"]
        if failing:
            reasons.append(f"VAL-01 non superato su {', '.join(failing)}")
    if not complete:
        return {"verdict": "INCOMPLETO", "reasons": reasons, "bases": per_base}
    return {"verdict": "NO-GO" if reasons else "GO", "reasons": reasons, "bases": per_base}


def _logs(logs: list[str]) -> str:
    return ", ".join(logs) if len(logs) <= 4 else f"{len(logs)} log ({', '.join(logs[:3])}, ...)"


def _cell(result: dict | None, metric: str) -> str:
    if result is None:
        return "—"
    if result["status"] != "measured":
        return {"out_of_budget": "fuori budget", "not_applicable": "non applicabile"}.get(result["status"], "fallito")
    m = result["metrics"][metric]
    text = f"{m['mean']:.3g} ± {m['ci95']:.2g}"
    return text if result["identifiability"].get(metric) == protocol.IDENTIFIABLE else f"{text} (NV)"


def _cost_cell(result: dict | None) -> str:
    c = cost(result)
    if c is None:
        return "—"
    sims = (result or {}).get("cost", {}).get("simulation_seconds") or [0.0]
    return f"{c[0]:.0f} s, {c[1]:.0f} MB, {max(sims):.1f} s/replica"


def report(results: dict) -> tuple[str, dict]:
    logs = [log.key for log in protocol.development_logs() if any(k[0] == log.key for k in results)]
    configs = sorted({k[2] for k in results}, key=lambda c: list(_order()).index(c) if c in _order() else 99)
    lines = [
        "# G3b: benchmark dei motori scientifici",
        "",
        "Generato da `tests/simulation/benchmark/g3b/report.py` dai file in `results/`.",
        "Distanze di B2 (tempi in ore, NGD in [0, 1]): media ± semiampiezza IC 95% su 10 repliche;",
        "(NV) = NOT VALIDATED sul periodo (PROTOCOL.md §4): calcolata, non conta. Più basso è meglio.",
        "",
        "## Verdetti delle schede",
        "",
        "| Componente | Fase | Verdetto | Motivi |",
        "| --- | --- | --- | --- |",
    ]
    verdicts = {}
    for card in CARDS:
        for phase in PHASES:
            v = verdict(card, phase, results, logs)
            verdicts[f"{card.component} / {phase}"] = v
            lines.append(f"| {card.component} | {phase} | **{v['verdict']}** | {'; '.join(v['reasons']) or '—'} |")
    lines += ["", "## Primaria contro ogni base", "", "Log dove la primaria è identificabile: vince / pari / perde.", "",
              "| Componente | Primaria | Base | Validazione | Test |", "| --- | --- | --- | --- | --- |"]
    for card in CARDS:
        for base in card.bases:
            cells = []
            for phase in PHASES:
                b = verdicts[f"{card.component} / {phase}"]["bases"].get(base)
                cells.append(f"{b['wins']} / {b['ties']} / {len(b['losses'])}" if b else "—")
            lines.append(f"| {card.component} | {LABELS[card.primary]} | {base} | " + " | ".join(cells) + " |")
    for phase in PHASES:
        lines += ["", f"## Metriche, fase {phase}", ""]
        for log in logs:
            lines += [f"### {log}", "", "| Configurazione | " + " | ".join(LABELS.values()) + " | Costo (tempo, picco, replica più lenta) |",
                      "|" + " --- |" * (len(LABELS) + 2)]
            for config in configs:
                r = results.get((log, phase, config))
                if r is None:
                    continue
                lines.append(f"| {r['label']} | " + " | ".join(_cell(r, m) for m in METRICS) + f" | {_cost_cell(r)} |")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n", verdicts


def _order() -> tuple[str, ...]:
    from tests.simulation.benchmark.g3b.run import CONFIGS

    return tuple(CONFIGS)


def main() -> int:
    text, verdicts = report(load_results())
    (HERE / "results.md").write_text(text, encoding="utf-8")
    (HERE / "verdicts.json").write_text(json.dumps(verdicts, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(text.split("## Metriche")[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
