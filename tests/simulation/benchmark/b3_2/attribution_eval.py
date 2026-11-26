"""B3.2: attribuzione delle attese contro la verita' dei sintetici (meta: >= 90% di cause giuste).

    /var/tmp/delir-g3b/envs/simod/bin/python tests/simulation/benchmark/b3_2/tools/truth_logs.py \\
        --inputs datasets/extraneous-delays/inputs/synthetic --out /var/tmp/delir-b32/truth/validation --seed 20261124 <nomi>
    (e --out /var/tmp/delir-b32/truth/test --seed 20261125)
    uv run python tests/simulation/benchmark/b3_2/attribution_eval.py --phase validation [--variant NOME]

**Verita'.** I log rigenerati dai modelli veri (``tools/truth_logs.py``) hanno per ogni
esecuzione l'abilitazione vera e i timer come eventi. L'attesa vera di un'esecuzione va dalla
fine dell'attivita' che la abilita all'inizio: il timer che finisce alla sua abilitazione e'
**ritardo esterno**; dall'abilitazione all'inizio ogni secondo e' **indisponibilita'** se la
risorsa e' fuori dal suo orario vero (JSON del modello), **congestione** se e' occupata in un
altro lavoro, altrimenti ``other`` (non dovrebbe esistere in Prosimos). Batching e sospensioni
non ci sono nei modelli: veri a zero.

**Attese contate.** Le esecuzioni non prime del caso (l'abilitazione della prima e' l'arrivo,
che il log non registra), con attesa vera o stimata oltre 1 s. Causa giusta = la causa con
piu' secondi coincide (``none`` se una delle due attese e' <= 1 s).

**Fasi.** ``validation`` = il log rigenerato con seed 20261124 (si sceglie qui), ``test`` = un
secondo log indipendente dello stesso modello, seed 20261125. L'attribuzione vede il log intero,
senza abilitazioni ne' timer. Non meta' dei casi: le risorse lavorano casi di entrambe le meta'
insieme, e un log dimezzato mostra buchi di lavoro che non esistono (valutazione 2, LOG.md).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from tests.simulation.benchmark.b3_2.attribution import CAUSES, Calendar, Execution, Waiting, _Busy, _merge, attribute

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
INPUTS = ROOT / "datasets" / "extraneous-delays" / "inputs" / "synthetic"
TRUTH = Path("/var/tmp/delir-b32/truth")
DAYS = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]
TIMER_LOGS = [f"{p}_{v}" for p in ("Insurance_Claims", "Loan_Application", "Pharmacy", "Procure_to_Pay")
              for v in ("1_timer", "3_timers", "5_timers", "5_timers_after")]
PLAIN_LOGS = ["Insurance_Claims", "Loan_Application", "Pharmacy", "Procure_to_Pay"]

# Varianti dell'attribuzione: ognuna con scheda in LOG.md prima della misura.
VARIANTS: dict[str, dict] = {
    "v1": {},
}


def _seconds(text: str) -> float:
    h, m, s = text.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def true_calendars(name: str) -> dict[str, Calendar]:
    """Profilo -> orario vero, dal JSON del modello (fine 23:59 = fino a mezzanotte)."""
    path = INPUTS / (name.removesuffix("_after") + ".json" if name.endswith("_after") else f"{name}.json")
    scenario = json.loads(path.read_text(encoding="utf-8"))
    calendars = {}
    for cal in scenario["resource_calendars"]:
        periods = []
        for p in cal["time_periods"]:
            lo, hi = _seconds(p["beginTime"]), _seconds(p["endTime"])
            hi = 86400.0 if hi >= 86340 else hi
            for day in range(DAYS.index(p["from"]), DAYS.index(p["to"]) + 1):
                periods.append((day * 86400 + lo, day * 86400 + hi))
        merged = _merge(periods)
        calendars[cal["id"]] = Calendar(always=True) if merged == [(0.0, float(7 * 86400))] else Calendar(merged)
    by_profile = {}
    for profile in scenario["resource_profiles"]:
        for resource in profile["resource_list"]:
            by_profile[resource["name"]] = calendars[resource["calendar"]]
    return by_profile


def _profile(resource: str, profiles: dict[str, Calendar]) -> Calendar:
    if resource in profiles:
        return profiles[resource]
    base = resource.rsplit("_", 1)[0]
    return profiles[base]


def load_truth(name: str, phase: str) -> tuple[list[Execution], list[Waiting]]:
    """Le esecuzioni (senza timer ne' abilitazioni) e le loro attese vere, nell'ordine del file."""
    with open(TRUTH / phase / f"{name}.csv", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    ts = lambda text: datetime.fromisoformat(text).timestamp()  # noqa: E731
    timers: dict[tuple[str, float], float] = {}
    executions, enabled = [], []
    for r in rows:
        if r["resource"] == "No assigned resource":
            timers[(r["case_id"], round(ts(r["end_time"]), 3))] = ts(r["start_time"])
        else:
            executions.append(Execution(r["case_id"], r["activity"], ts(r["start_time"]), ts(r["end_time"]), r["resource"]))
            enabled.append(ts(r["enable_time"]))
    profiles = true_calendars(name)
    work = defaultdict(list)
    for e in executions:
        work[e.resource].append((e.start, e.end))
    busy = {r: _Busy(v) for r, v in work.items()}
    first = {}
    for e in executions:
        first[e.case_id] = min(first.get(e.case_id, e.start), e.start)
    truths = []
    for e, en in zip(executions, enabled, strict=True):
        timer_start = timers.get((e.case_id, round(en, 3)))
        before = timer_start if timer_start is not None else en
        if e.start == first[e.case_id] and timer_start is None:
            truths.append(Waiting(None, dict.fromkeys(CAUSES, 0.0)))
            continue
        seconds = dict.fromkeys(CAUSES, 0.0)
        seconds["extraneous"] = en - before
        calendar = _profile(e.resource, profiles)
        seconds["unavailability"] = calendar.off_within(en, e.start)
        busy_on = _busy_on(busy[e.resource], en, e.start, calendar)
        seconds["contention"] = busy_on
        seconds["other"] = max(0.0, (e.start - en) - seconds["unavailability"] - busy_on)
        truths.append(Waiting(before, seconds))
    return executions, truths


def _busy_on(busy: _Busy, a: float, b: float, calendar: Calendar) -> float:
    total = 0.0
    for lo, hi in busy.intervals:
        lo, hi = max(lo, a), min(hi, b)
        if lo < hi:
            total += calendar.on_within(lo, hi)
    return total


def _dominant(w: Waiting) -> str:
    if w.enabled is None or w.total <= 1.0:
        return "none"
    return max([*CAUSES, "other"], key=lambda c: w.seconds.get(c, 0.0))


def evaluate(name: str, phase: str, variant: str) -> dict:
    executions, truths = load_truth(name, phase)
    predicted = attribute(executions, **VARIANTS[variant])
    confusion: Counter = Counter()
    seconds_right = seconds_total = 0.0
    for t, p in zip(truths, predicted, strict=True):
        if t.enabled is None or p.enabled is None:  # abilitazione non osservabile: fuori dal conteggio
            continue
        td, pd = _dominant(t), _dominant(p)
        if td == "none" and pd == "none":
            continue
        confusion[(td, pd)] += 1
        seconds_total += t.total
        seconds_right += sum(min(t.seconds.get(c, 0.0), p.seconds.get(c, 0.0)) for c in CAUSES)
    waits = sum(confusion.values())
    right = sum(n for (td, pd), n in confusion.items() if td == pd)
    return {"log": name, "phase": phase, "variant": variant, "waits": waits, "right": right,
            "accuracy": right / waits if waits else None,
            "seconds_share_right": seconds_right / seconds_total if seconds_total else None,
            "confusion": {f"{td}->{pd}": n for (td, pd), n in sorted(confusion.items())}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--phase", choices=("validation", "test"), required=True)
    parser.add_argument("--variant", default="v1", choices=list(VARIANTS))
    parser.add_argument("--logs", nargs="*", default=TIMER_LOGS + PLAIN_LOGS)
    parser.add_argument("--out", type=Path, default=HERE / "attribution")
    args = parser.parse_args(argv)
    results = [evaluate(name, args.phase, args.variant) for name in args.logs]
    timers = [r for r in results if r["log"] in TIMER_LOGS]
    pooled = sum(r["right"] for r in timers) / max(1, sum(r["waits"] for r in timers))
    for r in results:
        print(f"{r['log']:32} {r['waits']:6} {r['accuracy'] if r['accuracy'] is None else round(r['accuracy'], 3)!s:>6} "
              f"{r['confusion']}")
    print(f"16 log con timer: {pooled:.3f} ({sum(r['right'] for r in timers)}/{sum(r['waits'] for r in timers)})")
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / f"{args.phase}_{args.variant}.json").write_text(
        json.dumps({"pooled_timer_logs": pooled, "results": results}, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
