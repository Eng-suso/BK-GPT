"""L'event log della demo di lancio: un export del gestionale e l'analisi che ne fa DeliR.

Il caso e' fittizio come tutta la demo: l'export del workflow acquisti si ottiene
da un'altra run Prosimos dell'As-Is (seed diverso da quella mostrata, cosi' i
due non coincidono per costruzione) e registra le attivita' del processo con
l'utente che le esegue. In piu' la registrazione della fattura in
Amministrazione, subito dopo la verifica della merce, che nessuna intervista
racconta: l'analisi la trova come attivita' del log senza elemento nel modello.

Qualita', abbinamento e KPI li calcola `backend.eventlog.analysis.analyze`, la
stessa funzione della route di mapping. Esce `e2e/launch-media/data/eventlog.json`
e il CSV accanto.

    PYTHONPATH=. uv run python scripts/launch_media_eventlog.py
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.eventlog.analysis import analyze
from backend.eventlog.bpmn_match import ModelElement
from backend.eventlog.mapping import ColumnMapping
from backend.eventlog.readers import read_csv
from backend.simulation.bpmn_normalizer import normalize_bpmn_for_prosimos
from backend.simulation.ir.model import SimulationModel
from backend.simulation.log_processor import parse_prosimos_log
from backend.simulation.models import ProsimosSimulationRequest
from backend.simulation.prosimos_adapter import run_prosimos_simulation
from backend.simulation.result_parser import with_output_files
from backend.simulation.scenario_builder import build_prosimos_scenario_from_model, describe_scenario_template

DATA = Path("e2e/launch-media/data")
CSV_NAME = "export-workflow-acquisti.csv"
SEED = 7
CASES = 240

# Chi esegue che cosa, come lo scrive il workflow (utente per corsia).
USERS = {
    "Reparto": "reparto", "Ufficio Tecnico": "l.conti", "Ufficio Acquisti": "f.neri",
    "Responsabile Acquisti": "resp.acquisti", "Magazzino": "magazzino", "Amministrazione": "amministrazione",
}
INVOICE = "Registrazione fattura"


def finite(value):
    if isinstance(value, float) and value != value:
        return None
    if isinstance(value, dict):
        return {k: finite(v) for k, v in value.items()}
    if isinstance(value, list):
        return [finite(v) for v in value]
    return value


async def simulated_log(bpmn_xml: str, model: SimulationModel) -> str:
    scenario = build_prosimos_scenario_from_model(bpmn_xml=bpmn_xml, model=model)
    result = with_output_files(
        await run_prosimos_simulation(
            ProsimosSimulationRequest(
                bpmn_xml=bpmn_xml, scenario=scenario, total_cases=CASES, start_date="2026-06-01T08:00:00+02:00", seed=SEED
            )
        )
    )
    if not result.event_log_csv:
        raise RuntimeError("Prosimos non ha restituito il log")
    return result.event_log_csv


def export_csv(log_csv: str) -> str:
    rng = random.Random(SEED)
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";")
    writer.writerow(["Pratica", "Attivita", "Inizio", "Fine", "Utente"])
    fmt = lambda epoch: datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    received: dict[str, float] = {}
    for event in sorted(parse_prosimos_log(log_csv), key=lambda e: (int(e.case_id), e.start)):
        case = f"RDA-{2026}{int(event.case_id):04d}"
        writer.writerow([case, event.activity, fmt(event.start), fmt(event.end), USERS.get(event.resource.rsplit("_", 1)[0], "utente")])
        if event.activity == "Verifica merce ricevuta":
            received[case] = event.end
    for case, end in received.items():
        start = end + rng.uniform(10, 50) * 60
        writer.writerow([case, INVOICE, fmt(start), fmt(start + rng.uniform(10, 25) * 60), "amministrazione"])
    return out.getvalue()


async def main() -> None:
    runs = json.loads((DATA / "runs.json").read_text(encoding="utf-8"))
    source = (DATA / "as-is.bpmn").read_text(encoding="utf-8")
    bpmn_xml = normalize_bpmn_for_prosimos(source)
    model = SimulationModel.model_validate(runs["as_is"]["model"])
    text = export_csv(await simulated_log(bpmn_xml, model))
    (DATA / CSV_NAME).write_text(text, encoding="utf-8")

    table = read_csv(text.encode("utf-8"), ";")
    mapping = ColumnMapping(case_id=("Pratica",), activity=("Attivita",), start="Inizio", end="Fine", resource="Utente")
    template = describe_scenario_template(bpmn_xml, source_bpmn_xml=source)
    result = analyze(
        table,
        mapping,
        [ModelElement(task.element_id, task.name) for task in template.tasks],
        resources=[ModelElement(resource.id, resource.name) for resource in template.resources],
        source_name=CSV_NAME,
    )
    q = result.quality
    log = {
        "id": "elog-vetrano-erp",
        "process_id": "acquisti-indiretti",
        "name": CSV_NAME,
        "format": "csv",
        "delimiter": ";",
        "byte_size": len(text.encode("utf-8")),
        "row_count": len(table.rows),
        "columns": list(table.header),
        "status": "mapped",
        "mapping": json.loads(mapping.model_dump_json()),
        "template": None,
        "created_at": "2026-10-03T09:10:00Z",
        "mapped_at": "2026-10-03T09:12:00Z",
    }
    analysis = {
        "event_log": log,
        "quality": {
            "rows_read": q.rows_read, "rows_excluded": q.rows_excluded, "events": q.events, "cases": q.cases,
            "activities": q.activities, "resources": q.resources,
            "period_start": q.period_start.isoformat() if q.period_start else None,
            "period_end": q.period_end.isoformat() if q.period_end else None,
            "events_without_start": q.events_without_start,
            "issues": [
                {"code": i.code, "message": i.message, "count": i.count, "rows": list(i.rows), "excludes_rows": i.excludes_rows}
                for i in q.issues
            ],
        },
        "activities": {
            "bpmn_version_id": 3, "confirmed": True,
            "matches": [{"activity": m.activity, "events": m.events, "element_id": m.element_id, "reason": m.reason} for m in result.matches.matches],
            "unmatched_activities": list(result.matches.unmatched_activities),
            "unobserved_elements": [{"element_id": e.element_id, "name": e.name} for e in result.matches.unobserved_elements],
        },
        "resources": {
            "confirmed": False,
            "matches": [{"resource": m.activity, "events": m.events, "model_resource_id": m.element_id, "reason": m.reason} for m in result.resource_matches.matches],
            "unmatched_resources": list(result.resource_matches.unmatched_activities),
            "unobserved_model_resources": [{"resource_id": r.element_id, "name": r.name} for r in result.resource_matches.unobserved_elements],
            "events_without_resource": result.events_without_resource,
        },
        "summary": finite(result.summary),
    }
    preview = {"format": "csv", "delimiter": ";", "columns": list(table.header), "row_count": len(table.rows), "sample_rows": [list(r) for r in table.rows[:8]]}
    (DATA / "eventlog.json").write_text(json.dumps({"log": log, "preview": preview, "analysis": analysis}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"righe={len(table.rows)} casi={q.cases} attivita={q.activities} senza elemento={list(result.matches.unmatched_activities)}")


if __name__ == "__main__":
    asyncio.run(main())
