"""Spike G1: cosa sa fare Prosimos, provato con run veri, non letto nel README.

Ogni capacita' e' uno scenario separato sullo stesso BPMN, cosi' un fallimento
dice esattamente quale sezione del contratto il motore non regge. Lo stesso
scenario gira:

- nel processo, con il Prosimos installato in questo interprete (2.x richiede
  Python 3.11-3.12: va eseguito in un venv dedicato, non in quello del backend);
- opzionalmente via HTTP sul microservizio di sviluppo (oggi 1.2.6), con
  ``--service http://127.0.0.1:5000``.

Uso:
    python ops/prosimos/spike/contract_spike.py --out report.json
    python ops/prosimos/spike/contract_spike.py --service http://127.0.0.1:5000

Il risultato e' un JSON per capacita': esito, casi completati, e l'osservazione
che la capacita' ha davvero effetto (non solo che il parser l'ha accettata).
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import random
import statistics
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).parent
BPMN_PATH = HERE / "p2p_mini.bpmn"
START = "2026-01-05T09:00:00.000000+00:00"
CASES = 200


def _dist(name: str, *values: float) -> dict:
    return {"distribution_name": name, "distribution_params": [{"value": v} for v in values]}


def _period(day_from: str, day_to: str, begin: str, end: str) -> dict:
    return {"from": day_from, "to": day_to, "beginTime": begin, "endTime": end}


def base_scenario() -> dict:
    """La forma che DeliR manda oggi: un calendario, un pool per task, XOR statico."""
    office = [_period("MONDAY", "FRIDAY", "09:00:00", "17:00:00")]
    return {
        "resource_profiles": [
            {"id": "pool_ops", "name": "Operatori", "resource_list": [
                {"id": "ops", "name": "Operatore", "cost_per_hour": 30, "amount": 2,
                 "calendar": "cal_office", "assigned_tasks": ["T_receive", "T_pay"]}]},
            {"id": "pool_appr", "name": "Approvatori", "resource_list": [
                {"id": "appr", "name": "Approvatore", "cost_per_hour": 60, "amount": 1,
                 "calendar": "cal_office", "assigned_tasks": ["T_approve"]}]},
        ],
        "arrival_time_distribution": _dist("expon", 1800, 0, 18000),
        "arrival_time_calendar": office,
        "gateway_branching_probabilities": [
            {"gateway_id": "G_split", "probabilities": [
                {"path_id": "F_high", "value": 0.3}, {"path_id": "F_low", "value": 0.7}]},
        ],
        "task_resource_distribution": [
            {"task_id": "T_receive", "resources": [{"resource_id": "ops", **_dist("norm", 600, 120, 120, 1200)}]},
            {"task_id": "T_approve", "resources": [{"resource_id": "appr", **_dist("norm", 1800, 300, 600, 3600)}]},
            {"task_id": "T_pay", "resources": [{"resource_id": "ops", **_dist("norm", 900, 180, 300, 1800)}]},
        ],
        "resource_calendars": [{"id": "cal_office", "name": "Ufficio", "time_periods": office}],
        "event_distribution": [],
        "batch_processing": [],
        "case_attributes": [],
    }


# --------------------------------------------------------------------------- #
# Le capacita': ognuna modifica lo scenario base e dice come verificare l'effetto
# --------------------------------------------------------------------------- #


def cap_calendars(s: dict) -> dict:
    """Calendari diversi per pool: gli approvatori lavorano lun-gio 10-14."""
    s["resource_calendars"].append({"id": "cal_appr", "name": "Approvazioni",
                                    "time_periods": [_period("MONDAY", "THURSDAY", "10:00:00", "14:00:00")]})
    s["resource_profiles"][1]["resource_list"][0]["calendar"] = "cal_appr"
    return s


def check_calendars(rows: list[dict]) -> str | None:
    bad = [r for r in rows if r["activity"] == "Approva" and not _within(r, {0, 1, 2, 3}, 10, 14)]
    return None if not bad else f"{len(bad)} approvazioni fuori calendario"


def cap_distributions(s: dict) -> dict:
    """Le famiglie che pix-framework dichiara: uniform, triang, lognorm, gamma."""
    t = s["task_resource_distribution"]
    t[0]["resources"][0].update(_dist("uniform", 300, 900))
    t[1]["resources"][0].update(_dist("lognorm", 1800, 360000, 300, 7200))
    t[2]["resources"][0].update(_dist("gamma", 900, 40000, 200, 3600))
    return s


def cap_triangular(s: dict) -> dict:
    s["task_resource_distribution"][0]["resources"][0].update(_dist("triang", 300, 600, 1200))
    return s


def cap_case_attributes(s: dict) -> dict:
    s["case_attributes"] = [
        {"name": "tipo", "type": "discrete", "values": [
            {"key": "premium", "value": 0.2}, {"key": "standard", "value": 0.8}]},
        {"name": "importo", "type": "continuous", "values": _dist("uniform", 100, 12000)},
    ]
    return s


def cap_branch_rules(s: dict) -> dict:
    """Routing condizionale: importo > 5000 -> seconda approvazione."""
    s = cap_case_attributes(s)
    s["branch_rules"] = [
        {"id": "r_high", "rules": [[{"attribute": "importo", "comparison": ">", "value": "5000"}]]},
        {"id": "r_low", "rules": [[{"attribute": "importo", "comparison": "<=", "value": "5000"}]]},
    ]
    s["gateway_branching_probabilities"][0]["probabilities"] = [
        {"path_id": "F_high", "value": 0.5, "condition_id": "r_high"},
        {"path_id": "F_low", "value": 0.5, "condition_id": "r_low"},
    ]
    return s


def check_branch_rules(rows: list[dict]) -> str | None:
    wrong = 0
    for events in _by_case(rows).values():
        amount = _attr(events, "importo")
        if amount is None:
            return "attributo importo assente dal log: regola non verificabile"
        approved = any(e["activity"] == "Approva" for e in events)
        wrong += approved != (amount > 5000)
    return None if wrong == 0 else f"{wrong} casi instradati contro la regola"


def cap_prioritisation(s: dict) -> dict:
    s = cap_case_attributes(s)
    s["prioritisation_rules"] = [
        {"priority_level": 1, "rules": [[{"attribute": "tipo", "comparison": "=", "value": "premium"}]]},
        {"priority_level": 2, "rules": [[{"attribute": "tipo", "comparison": "=", "value": "standard"}]]},
    ]
    # Coda vera: arrivi fitti, un solo operatore.
    s["arrival_time_distribution"] = _dist("expon", 400, 0, 4000)
    s["resource_profiles"][0]["resource_list"][0]["amount"] = 1
    return s


def check_prioritisation(rows: list[dict]) -> str | None:
    waits: dict[str, list[float]] = {"premium": [], "standard": []}
    for events in _by_case(rows).values():
        kind = _attr(events, "tipo")
        first = min(events, key=lambda e: e["start"])
        if kind in waits:
            waits[kind].append(first["start"] - first["enable"])
    if not waits["premium"] or not waits["standard"]:
        return "attributo tipo assente dal log: priorita' non verificabile"
    p, s = statistics.mean(waits["premium"]), statistics.mean(waits["standard"])
    return None if p < s else f"premium non attende meno (premium {p:.0f}s, standard {s:.0f}s)"


def cap_event_attributes(s: dict) -> dict:
    """Mutazione: dopo Ricevi il caso guadagna `rischio = importo / 1000`."""
    s = cap_case_attributes(s)
    s["event_attributes"] = [
        {"event_id": "T_receive", "attributes": [
            {"name": "rischio", "type": "expression", "values": "importo / 1000"}]},
    ]
    return s


def check_event_attributes(rows: list[dict]) -> str | None:
    for events in _by_case(rows).values():
        risk, amount = _attr(events, "rischio"), _attr(events, "importo")
        if risk is None:
            return "attributo rischio assente dal log"
        if amount is not None and abs(risk - amount / 1000) > 1e-6:
            return f"rischio {risk} diverso da importo/1000 ({amount})"
    return None


def cap_batching(s: dict) -> dict:
    s["batch_processing"] = [{
        "task_id": "T_pay", "type": "Sequential", "size_distrib": [{"key": "3", "value": 1}],
        "duration_distrib": [{"key": "3", "value": 0.8}],
        "firing_rules": [[{"attribute": "size", "comparison": "=", "value": 3}]],
    }]
    return s


CAPABILITIES: dict[str, tuple[Callable[[dict], dict], Callable[[list[dict]], str | None] | None]] = {
    "baseline": (lambda s: s, None),
    "calendari_per_pool": (cap_calendars, check_calendars),
    "distribuzioni_uniform_lognorm_gamma": (cap_distributions, None),
    "distribuzione_triangolare": (cap_triangular, None),
    "attributi_caso": (cap_case_attributes, None),
    "routing_condizionale": (cap_branch_rules, check_branch_rules),
    "priorita_coda": (cap_prioritisation, check_prioritisation),
    "attributi_evento_espressione": (cap_event_attributes, check_event_attributes),
    "batch": (cap_batching, None),
}


# --------------------------------------------------------------------------- #
# Esecuzione
# --------------------------------------------------------------------------- #


def run_in_process(scenario: dict, seed: int | None = None) -> str:
    from prosimos.simulation_engine import run_simulation

    if seed is not None:
        # Prosimos non espone un seed: usa `random` e `numpy.random` globali.
        import numpy

        random.seed(seed)
        numpy.random.seed(seed)
    with tempfile.TemporaryDirectory() as tmp:
        json_path = Path(tmp) / "scenario.json"
        log_path = Path(tmp) / "log.csv"
        json_path.write_text(json.dumps(scenario))
        run_simulation(str(BPMN_PATH), str(json_path), CASES, None, str(log_path), START)
        return log_path.read_text()


def run_on_service(scenario: dict, base_url: str) -> str:
    import httpx

    files = {
        "modelFile": ("model.bpmn", BPMN_PATH.read_bytes(), "text/xml"),
        "simScenarioFile": ("scenario.json", json.dumps(scenario).encode(), "application/json"),
    }
    data = {"startDate": START, "numProcesses": str(CASES)}
    with httpx.Client(timeout=300) as client:
        response = client.post(f"{base_url}/api/simulate", data=data, files=files)
        response.raise_for_status()
        logs = response.json()["LogsFilename"]
        return client.get(f"{base_url}/api/simulationFile", params={"fileName": logs}).text


def parse_log(text: str) -> list[dict]:
    from datetime import datetime

    def ts(raw: str) -> float:
        return datetime.fromisoformat(raw.replace(" ", "T")).timestamp()

    rows = []
    for row in csv.DictReader(io.StringIO(text)):
        parsed: dict[str, Any] = dict(row)
        parsed["enable"], parsed["start"], parsed["end"] = (
            ts(row["enable_time"]), ts(row["start_time"]), ts(row["end_time"]))
        parsed["_raw_start"] = row["start_time"]
        rows.append(parsed)
    return rows


def _by_case(rows: list[dict]) -> dict[str, list[dict]]:
    cases: dict[str, list[dict]] = {}
    for row in rows:
        cases.setdefault(row["case_id"], []).append(row)
    return cases


def _attr(events: list[dict], name: str) -> Any:
    for event in reversed(events):
        raw = event.get(name)
        if raw not in (None, ""):
            try:
                return float(raw)
            except ValueError:
                return raw
    return None


def _within(row: dict, weekdays: set[int], hour_from: int, hour_to: int) -> bool:
    from datetime import datetime

    start = datetime.fromisoformat(row["_raw_start"].replace(" ", "T"))
    end = datetime.fromtimestamp(row["end"], tz=start.tzinfo)
    return (start.weekday() in weekdays and hour_from <= start.hour < hour_to
            and end.weekday() in weekdays and (hour_from <= end.hour < hour_to
                                               or (end.hour == hour_to and end.minute == 0)))


def evaluate(name: str, runner: Callable[[dict], str]) -> dict:
    build, check = CAPABILITIES[name]
    try:
        rows = parse_log(runner(build(deepcopy(base_scenario()))))
    except Exception as exc:  # noqa: BLE001 - lo spike registra il fallimento, non si ferma
        return {"esito": "errore", "dettaglio": f"{type(exc).__name__}: {exc}"[:300]}
    cases = len(_by_case(rows))
    problem = check(rows) if check else None
    return {
        "esito": "ok" if problem is None and cases > 0 else "effetto_assente",
        "casi": cases,
        "colonne_log": sorted(k for k in rows[0] if not k.startswith("_") and k not in ("enable", "start", "end")) if rows else [],
        "dettaglio": problem,
    }


def check_seed() -> dict:
    """Stesso seed, stesso log? Seed diversi, log diversi?"""
    scenario = base_scenario()
    a, b, c = (run_in_process(scenario, 7), run_in_process(scenario, 7), run_in_process(scenario, 8))
    return {"stesso_seed_identico": a == b, "seed_diverso_differente": a != c}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", help="URL del microservizio Prosimos da provare via HTTP")
    parser.add_argument("--out", type=Path, help="dove scrivere il report JSON")
    args = parser.parse_args()

    report: dict[str, Any] = {"casi_per_run": CASES}
    if args.service:
        report["motore"] = f"servizio {args.service}"
        report["capacita"] = {n: evaluate(n, lambda s: run_on_service(s, args.service)) for n in CAPABILITIES}
    else:
        from importlib.metadata import version

        report["motore"] = f"prosimos {version('prosimos')} nel processo, Python {sys.version.split()[0]}"
        report["capacita"] = {n: evaluate(n, run_in_process) for n in CAPABILITIES}
        report["seed"] = check_seed()
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
