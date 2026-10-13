"""As-Is e To-Be del processo demo dei video (`e2e/launch-media/data/demo.bpmn`).

Stessa pipeline di `scripts/launch_media_simulate.py` (BPMN normalizzato,
modello IR, Prosimos, summary e replay dal log), sul processo semplice
"Gestione richiesta di acquisto". Ogni parametro dice da dove viene:

- `declared` solo per cio' che una fonte dice davvero;
- un numero che il consulente sceglie partendo da una fonte e' `manual` con la
  fonte allegata e la nota "La fonte dice ... Valore scelto dal consulente ..."
  (`estimated` qui sotto): la citazione regge il fatto, non il valore;
- cio' che nessuna fonte tocca e' `manual` senza fonti (`assumed`).

Nessun parametro si ritocca per far tornare i numeri: il risultato e' quello
che il modello produce.

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
    AUTH_SHARE,
    DATA,
    RESPONSABILE_AS_IS,
    RESPONSABILE_TO_BE,
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


def estimated(*who: str, said: str, chosen: str) -> dict:
    """Un numero scelto dal consulente a partire da cio' che la fonte dice.

    La fonte regge il fatto, non il valore: origine `manual` (il numero e' del
    consulente), con la fonte da cui parte e la nota che separa le due cose.
    """
    return {
        **declared(*who, note=f"La fonte dice: {said} Valore scelto dal consulente: {chosen}"),
        "origin": "manual",
        "confidence": "low",
    }


# Minuti di lavoro (processing time) per attivita'. Le interviste dicono che il
# passo esiste e dove si perde tempo, non quanto dura il gesto: le durate sono
# tutte del consulente, con la fonte del passo quando c'e'.
DURATIONS = {
    "Task_Compila": (
        lognormal(15, 12, 120),
        estimated(
            "laura",
            said="\"Quindi comincia il giro di telefonate.\" e da dieci minuti a due giorni.",
            chosen="lavoro effettivo da 15 minuti a 2 ore. I due giorni sono tempo trascorso in attesa delle "
            "risposte, che qui non e' modellato: il ciclo simulato lo sottostima.",
        ),
    ),
    "Task_Invia": (normal(5, 1), estimated("paolo", said="\"Mail. Sempre mail, a Laura.\"", chosen="5 minuti.")),
    "Task_Verifica": (normal(10, 3), estimated("francesca", said="\"Leggo e verifico se e' lavorabile.\"", chosen="10 minuti.")),
    "Path_Integrazione_Task_Richiedi": (
        normal(10, 3),
        estimated("francesca", said="che rimanda indietro le richieste incomplete.", chosen="10 minuti."),
    ),
    "Path_Integrazione_Task_Integra": (lognormal(20, 15, 240), assumed("Nessuna fonte descrive il passo: durata del consulente.")),
    "Task_Valuta": (
        normal(10, 3),
        estimated("francesca", said="\"e' una mail che mando e una risposta che aspetto.\"", chosen="10 minuti di lavoro del responsabile."),
    ),
    "Path_Rifiuto_Task_Rifiuto": (normal(5, 1), assumed("Nessuna fonte descrive il rifiuto: durata del consulente.")),
    "Task_Emetti": (normal(10, 3), estimated("francesca", said="\"emetto l'ordine e via.\"", chosen="10 minuti.")),
}

# Il responsabile: la fonte dice che manca a lungo e che nessuno lo sostituisce,
# non quando c'e'. Il calendario e' quello del modello esteso
# (scripts/launch_media_simulate.py), dichiarato come scelta del consulente.
RESPONSABILE_PROVENANCE = estimated(
    "francesca",
    said="\"Se e' fuori, possono essere giorni. Non c'e' un sostituto formale\".",
    chosen="disponibile un'ora il martedi' e un'ora il giovedi'. Nessuna fonte quantifica la presenza.",
)

# corsia -> (persone, costo orario): nessuna fonte lo dice
RESOURCES = {"Reparto richiedente": (4, 38.0), "Ufficio Acquisti": (1, 45.0), "Responsabile Acquisti": (1, 70.0)}

COMPLETA_SI, COMPLETA_NO = "Flow_Decision_Completa_to_Decision_Necessaria", "Flow_Decision_Completa_to_Path_Integrazione_Task_Richiedi"
NECESSARIA_SI, NECESSARIA_NO = "Flow_Decision_Necessaria_to_Task_Valuta", "Flow_Decision_Necessaria_to_Task_Emetti"
AUTORIZZATA_SI, AUTORIZZATA_NO = "Flow_Decision_Autorizzata_to_Task_Emetti", "Flow_Decision_Autorizzata_to_Path_Rifiuto_Task_Rifiuto"
incomplete = estimated("francesca", said="\"A sensazione, piu' della meta'.\" (oltre il 50%)", chosen="55%.")
threshold = assumed(
    "Quota sopra la soglia di autorizzazione: la soglia e' una lacuna aperta (nessuna fonte la dice) e la "
    "distribuzione degli importi non e' nota. Un terzo, come nel modello esteso: parametro incerto da far variare."
)
BRANCHES = {
    COMPLETA_NO: (0.55, incomplete),
    COMPLETA_SI: (0.45, incomplete),
    NECESSARIA_SI: (AUTH_SHARE, threshold),
    NECESSARIA_NO: (1 - AUTH_SHARE, threshold),
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
                resource["provenance"] = RESPONSABILE_PROVENANCE
    for activity in data["activities"]:
        duration, provenance = DURATIONS[activity["element_id"]]
        for assignment in activity["assignments"]:
            assignment["duration"], assignment["provenance"] = duration, provenance
    for gateway in data["gateways"]:
        for branch in gateway["branches"]:
            branch["probability"], branch["provenance"] = BRANCHES[branch["flow_id"]]
    return SimulationModel.model_validate(data)


def to_be_model(as_is: SimulationModel) -> SimulationModel:
    """Una richiesta delle fonti e un'ipotesi del consulente, ciascuna con la sua provenienza.

    - Richiesta completa all'origine: la chiede Francesca. L'effetto sui rimbalzi
      e sul tempo di compilazione e' una stima del consulente.
    - Delega dell'autorizzazione: ipotesi del consulente, non di Francesca. Parte
      dal problema che lei descrive (nessun sostituto formale). La sua richiesta
      di un'autorizzazione "che si vede" non cambia nessun parametro: non e' simulata.
    """
    data = as_is.model_dump(mode="json")
    form = estimated(
        "francesca",
        said="\"Farei in modo che la richiesta nasca gia' completa, con i campi obbligatori.\"",
        chosen="rimbalzi dal 55% al 25%, compilazione da 15 a 8 minuti.",
    )
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
    delegate = estimated(
        "francesca",
        said="\"Non c'e' un sostituto formale\": e' il problema, la delega non la propone lei.",
        chosen="ipotesi del consulente: un delegato autorizza un'ora ogni giorno lavorativo.",
    )
    data["calendars"].append({"id": "responsabile-con-delega", "name": "Autorizzazione ogni giorno (delega)", "periods": RESPONSABILE_TO_BE})
    for pool in data["pools"]:
        for resource in pool["resources"]:
            if resource["name"] == "Responsabile Acquisti":
                resource["calendar_id"], resource["provenance"] = "responsabile-con-delega", delegate
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
