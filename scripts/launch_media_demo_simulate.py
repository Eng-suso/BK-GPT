"""As-Is e To-Be del processo demo dei video (`e2e/launch-media/data/demo.bpmn`).

Stessa pipeline di `scripts/launch_media_simulate.py` (BPMN normalizzato,
modello IR, Prosimos, summary e replay dal log), sul processo semplice
"Gestione richiesta di acquisto". I parametri citano le interviste del golden
set quando le dicono; il resto e' assunzione del consulente, dichiarata.

Esce `e2e/launch-media/data/demo-runs.json` (run) e `demo-api.json` (template,
provenienza e compatibilita' come le darebbe il backend).

Serve il runner Prosimos (`ops/prosimos/runner`) su PROSIMOS_BASE_URL:

    PYTHONPATH=. uv run python scripts/launch_media_demo_simulate.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from launch_media_simulate import (  # noqa: E402
    DATA,
    WORKDAY,
    assumed,
    declared,
    finite,
    lognormal,
    normal,
    run,
)

from backend.simulation.advisor import suggest_experiments  # noqa: E402
from backend.simulation.bpmn_normalizer import normalize_bpmn_for_prosimos  # noqa: E402
from backend.simulation.compatibility import bpmn_compatibility_report  # noqa: E402
from backend.simulation.ir.model import SimulationModel  # noqa: E402
from backend.simulation.scenario_builder import baseline_for_bpmn, describe_scenario_template  # noqa: E402

SOURCE = DATA / "demo.bpmn"

# Minuti di lavoro per attivita'. Le interviste dicono dove si perde tempo
# (ricostruire la richiesta, rimbalzarla, aspettare l'autorizzazione), non
# quanto dura ogni gesto: i gesti brevi sono assunzioni.
DURATIONS = {
    "Task_Compila": (
        lognormal(15, 12, 120),
        declared("laura", note="\"Comincia il giro di telefonate. A volte lo risolvo in dieci minuti, a volte ci metto due giorni.\""),
    ),
    "Task_Invia": (normal(5, 1), declared("paolo", note="\"Mail. Sempre mail, a Laura.\"")),
    "Task_Verifica": (normal(10, 3), declared("francesca", note="\"Leggo e verifico se e' lavorabile.\"")),
    "Path_Integrazione_Task_Richiedi": (normal(10, 3), declared("francesca", note="\"Rimbalzare indietro le richieste per completarle.\"")),
    "Path_Integrazione_Task_Integra": (lognormal(20, 15, 240), assumed("Tempo per integrare la richiesta: assunzione del consulente.")),
    "Task_Valuta": (
        normal(5, 1),
        declared("francesca", note="\"E' una mail che mando e una risposta che aspetto.\" Durata della risposta: assunzione."),
    ),
    "Path_Rifiuto_Task_Rifiuto": (normal(5, 1), assumed("Durata della comunicazione: assunzione del consulente.")),
    "Task_Emetti": (normal(10, 3), declared("francesca", note="\"Emetto l'ordine e via.\"")),
}

# Qui ogni richiesta completa passa dal responsabile (nel modello esteso solo
# quelle sopra soglia): c'e' due pomeriggi a settimana e nessuno lo sostituisce
# (Francesca). Nel To-Be un delegato autorizza ogni giorno.
RESPONSABILE_AS_IS = [
    {"from_day": "TUESDAY", "to_day": "TUESDAY", "begin": "16:00:00.000", "end": "18:00:00.000"},
    {"from_day": "THURSDAY", "to_day": "THURSDAY", "begin": "16:00:00.000", "end": "18:00:00.000"},
]
RESPONSABILE_TO_BE = [{"from_day": "MONDAY", "to_day": "FRIDAY", "begin": "16:00:00.000", "end": "17:00:00.000"}]

# corsia -> (persone, costo orario): nessuna fonte lo dice
RESOURCES = {"Reparto richiedente": (4, 38.0), "Ufficio Acquisti": (1, 45.0), "Responsabile Acquisti": (1, 70.0)}

COMPLETA_SI, COMPLETA_NO = "Flow_Decision_Completa_to_Task_Valuta", "Flow_Decision_Completa_to_Path_Integrazione_Task_Richiedi"
AUTORIZZATA_SI, AUTORIZZATA_NO = "Flow_Decision_Autorizzata_to_Task_Emetti", "Flow_Decision_Autorizzata_to_Path_Rifiuto_Task_Rifiuto"
BRANCHES = {
    COMPLETA_NO: (0.55, declared("francesca", note="\"A sensazione, piu' della meta'.\"")),
    COMPLETA_SI: (0.45, declared("francesca", note="\"A sensazione, piu' della meta'.\"")),
    AUTORIZZATA_SI: (0.9, assumed("Quota di richieste autorizzate: nessuna fonte la dice, assunzione del consulente.")),
    AUTORIZZATA_NO: (0.1, assumed("Quota di richieste respinte: nessuna fonte la dice, assunzione del consulente.")),
}


def as_is_model(base: SimulationModel) -> SimulationModel:
    data = base.model_dump(mode="json")
    data["arrival"]["interarrival"] = {"kind": "exponential", "mean": WORKDAY / 5, "minimum": 0.0, "maximum": WORKDAY}
    data["arrival"]["provenance"] = assumed("Volume: circa 5 richieste al giorno. Nessuna fonte lo dice: assunzione del consulente.")
    data["calendars"].append({"id": "responsabile-assente", "name": "Responsabile presente a tratti", "periods": RESPONSABILE_AS_IS})
    for pool in data["pools"]:
        for resource in pool["resources"]:
            amount, cost = RESOURCES[resource["name"]]
            resource["amount"], resource["cost_per_hour"] = amount, cost
            resource["provenance"] = assumed("Persone e costo orario: assunzione del consulente.")
            if resource["name"] == "Responsabile Acquisti":
                resource["calendar_id"] = "responsabile-assente"
                resource["provenance"] = declared(
                    "francesca", note="\"Se e' fuori, possono essere giorni. Non c'e' un sostituto formale.\""
                )
    for activity in data["activities"]:
        duration, provenance = DURATIONS[activity["element_id"]]
        for assignment in activity["assignments"]:
            assignment["duration"], assignment["provenance"] = duration, provenance
    for gateway in data["gateways"]:
        for branch in gateway["branches"]:
            branch["probability"], branch["provenance"] = BRANCHES[branch["flow_id"]]
    return SimulationModel.model_validate(data)


def to_be_model(as_is: SimulationModel) -> SimulationModel:
    """Solo cio' che gli intervistati hanno chiesto: richiesta completa e autorizzazione visibile."""
    data = as_is.model_dump(mode="json")
    form = {
        **declared(
            "francesca",
            note="To-Be: \"Farei in modo che la richiesta nasca gia' completa, con i campi obbligatori.\" "
            "Effetto stimato (rimbalzi dal 55% al 25%): assunzione del consulente.",
        ),
        "origin": "manual",
        "confidence": "low",
    }
    for gateway in data["gateways"]:
        for branch in gateway["branches"]:
            if branch["flow_id"] == COMPLETA_NO:
                branch["probability"], branch["provenance"] = 0.25, form
            elif branch["flow_id"] == COMPLETA_SI:
                branch["probability"], branch["provenance"] = 0.75, form
    for activity in data["activities"]:
        if activity["element_id"] == "Task_Compila":
            for assignment in activity["assignments"]:
                assignment["duration"], assignment["provenance"] = normal(8, 3), form
    data["calendars"].append({"id": "responsabile-con-delega", "name": "Autorizzazione ogni giorno (delega)", "periods": RESPONSABILE_TO_BE})
    for pool in data["pools"]:
        for resource in pool["resources"]:
            if resource["name"] == "Responsabile Acquisti":
                resource["calendar_id"] = "responsabile-con-delega"
                resource["provenance"] = {
                    **declared(
                        "francesca",
                        note="To-Be: \"E vorrei che l'autorizzazione fosse una cosa che si vede, non una mail che aspetto.\" "
                        "Delega con una finestra al giorno: assunzione del consulente.",
                    ),
                    "origin": "manual",
                    "confidence": "low",
                }
    return SimulationModel.model_validate(data)


async def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    bpmn_xml = normalize_bpmn_for_prosimos(source)
    as_is = as_is_model(baseline_for_bpmn(bpmn_xml, source_bpmn_xml=source))
    runs = {
        "as_is": await run("As-Is · validato", bpmn_xml, as_is),
        "to_be": await run("To-Be · richiesta completa + delega", bpmn_xml, to_be_model(as_is)),
    }
    for value in runs.values():
        value["experiments"] = suggest_experiments(value["summary"], value["scenario"]).model_dump(mode="json")
    (DATA / "demo-runs.json").write_text(json.dumps(finite(runs), ensure_ascii=False, allow_nan=False), encoding="utf-8")
    template = describe_scenario_template(bpmn_xml, source_bpmn_xml=source)
    api = {
        "simulation_template": template.model_dump(mode="json"),
        "simulation_compatibility": bpmn_compatibility_report(source).model_dump(mode="json"),
    }
    (DATA / "demo-api.json").write_text(json.dumps(finite(api), ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8")
    for key, value in runs.items():
        s = value["summary"]
        print(
            key,
            f"casi={s['casesCompleted']}",
            f"ciclo_medio_gg={s['cycle']['avg'] / 86400:.2f}",
            f"attesa={s['waiting']['share']:.0%}",
            f"costo_caso={s['cost']['perCase']:.2f}",
            f"collo={s.get('bottleneck', {}).get('name') if s.get('bottleneck') else None}",
        )


if __name__ == "__main__":
    asyncio.run(main())
