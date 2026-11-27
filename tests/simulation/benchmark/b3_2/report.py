"""B3.2: verdetti delle schede 1 e 3 (LOG.md) dai risultati di ``run.py``, con le regole di G3b.

    uv run python tests/simulation/benchmark/b3_2/report.py

Scrive ``results.md`` e ``verdicts.json``. La scheda 2 (attribuzione sui sintetici) ha il suo
comando: ``attribution_eval.py``. Le regole sono quelle di ``g3b/report.py::verdict``
(PROTOCOL.md §7); la scheda 3 ha due primarie, W1 e RED: e' GO se lo sono entrambe.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

if __package__ in (None, ""):  # lanciato come script
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from tests.simulation.benchmark import protocol
from tests.simulation.benchmark.b3_2.run import CONFIGS, RESULTS
from contextlib import contextmanager

from tests.simulation.benchmark.g3b import report as g3b_report
from tests.simulation.benchmark.g3b.report import LABELS, Card, _cell, _cost_cell
from tests.simulation.benchmark.g3b.run import PHASES
from tests.simulation.benchmark.log_distance import METRICS

HERE = Path(__file__).resolve().parent
REAL = ("AcademicCredentials", "BPIC_2012_W", "BPIC_2017_W")
NOT_RED = ("bpic2012", "bpic2013_incidents")  # RED NOT VALIDATED (PROTOCOL.md §4)

# (scheda, carta, log)
CARDS = (
    ("1", Card("Ablazione dei ritardi estranei", "simod_fixed_extr", ("simod",), "relative_event", "scenario"), None),
    ("3", Card("Attese attribuite: W1", "simod_attr_extr", ("simod_extr",), "cycle_time_w1", "scenario"), REAL),
    ("3", Card("Attese attribuite: RED", "simod_attr_extr", ("simod_extr",), "relative_event", "scenario"), REAL),
    ("3b", Card("Attese attribuite v2: W1", "simod_attr_idle", ("simod_extr",), "cycle_time_w1", "scenario"), REAL),
    ("3b", Card("Attese attribuite v2: RED", "simod_attr_idle", ("simod_extr",), "relative_event", "scenario"), REAL),
    ("3c", Card("Attese attribuite v3: W1", "simod_attr_shift", ("simod_extr",), "cycle_time_w1", "scenario"), REAL),
    ("3c", Card("Attese attribuite v3: RED", "simod_attr_shift", ("simod_extr",), "relative_event", "scenario"), REAL),
    ("3d", Card("Attese attribuite v4: W1", "simod_attr_closest", ("simod_extr",), "cycle_time_w1", "scenario"), REAL),
    ("3d", Card("Attese attribuite v4: RED", "simod_attr_closest", ("simod_extr",), "relative_event", "scenario"), REAL),
)


def compare(candidate: dict | None, base: dict | None, metric: str) -> str:
    """Come ``g3b/report.py::compare``, ma due risultati identici sono pari.

    In G3b ``within_intervals`` usa ``<``: due medie uguali con intervalli nulli (sintetici di un
    giorno, scenari identici) risultano "diverse" e il candidato perde. Qui il caso e' frequente
    (la fase dei ritardi di SIMOD spesso non mette timer: scenario uguale alla base). ``g3b`` non
    si tocca (vincolo di B3.2); la correzione e' proposta a Sohayb in LOG.md.
    """
    if g3b_report.measured(candidate) and g3b_report.measured(base) and candidate["metrics"][metric] == base["metrics"][metric]:
        return "pari"
    return _g3b_compare(candidate, base, metric)


_g3b_compare = g3b_report.compare


@contextmanager
def _ties_for_identical():
    """``g3b_report.verdict`` con il ``compare`` di qui, solo dentro questo blocco."""
    g3b_report.compare = compare
    try:
        yield
    finally:
        g3b_report.compare = _g3b_compare


def verdict(card: Card, phase: str, results: dict, logs: list[str]) -> dict:
    with _ties_for_identical():
        return g3b_report.verdict(card, phase, results, logs)


def load_results() -> dict[tuple[str, str, str], dict]:
    return {(p.parts[-3], p.parts[-2], p.stem): json.loads(p.read_text(encoding="utf-8")) for p in sorted(RESULTS.glob("*/*/*.json"))}


def report(results: dict) -> tuple[str, dict]:
    all_logs = [log.key for log in protocol.development_logs() if log.key not in NOT_RED]
    lines = ["# B3.2: discovery delle attese", "",
             "Generato da `tests/simulation/benchmark/b3_2/report.py`. Distanze di B2 (ore, NGD in [0, 1]), media ±",
             "semiampiezza IC 95% su 10 repliche; (NV) = NOT VALIDATED. Più basso è meglio. Regole di `g3b/report.py`.", "",
             "## Verdetti", "", "| Scheda | Componente | Fase | Verdetto | V / P / P | Motivi |", "| --- | --- | --- | --- | --- | --- |"]
    verdicts = {}
    for number, card, logs in CARDS:
        logs = [log for log in (logs or all_logs) if any(k[0] == log for k in results)]
        for phase in PHASES:
            if not any(k[1] == phase and k[2] == card.candidate for k in results):
                continue
            v = verdict(card, phase, results, logs)
            verdicts[f"{number} {card.component} / {phase}"] = v
            b = v["bases"].get(card.bases[0])
            score = f"{b['wins']} / {b['ties']} / {len(b['losses'])}" if b else "—"
            lines.append(f"| {number} | {card.component} | {phase} | **{v['verdict']}** | {score} | {'; '.join(v['reasons']) or '—'} |")
    configs = [c for c in CONFIGS if any(k[2] == c for k in results)]
    for phase in PHASES:
        lines += ["", f"## Metriche, fase {phase}", ""]
        for log in all_logs:
            rows = [results[(log, phase, c)] for c in configs if (log, phase, c) in results]
            if not rows:
                continue
            lines += [f"### {log}", "", "| Configurazione | " + " | ".join(LABELS.values()) + " | Costo | Ritardi (s, media) |",
                      "|" + " --- |" * (len(LABELS) + 3)]
            for r in rows:
                delays = r.get("cost", {}).get("delays")
                shown = ", ".join(f"{a}: {s:.0f}" for a, s in list(delays.items())[:4]) + (" …" if len(delays) > 4 else "") if delays else "—"
                lines.append(f"| {r['config']} | " + " | ".join(_cell(r, m) for m in METRICS) + f" | {_cost_cell(r)} | {shown} |")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n", verdicts


def main() -> int:
    text, verdicts = report(load_results())
    (HERE / "results.md").write_text(text, encoding="utf-8")
    (HERE / "verdicts.json").write_text(json.dumps(verdicts, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(text.split("## Metriche")[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
