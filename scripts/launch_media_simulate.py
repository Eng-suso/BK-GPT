"""Le due simulazioni vere della demo di lancio: As-Is e To-Be, stesso motore del prodotto.

Ripete la pipeline di `backend/simulation/service.py` senza database: BPMN
normalizzato, modello IR, scenario Prosimos, run sul runner, poi summary e
replay dal log completo. Il risultato va in `e2e/launch-media/data/runs.json`
e lo spec di cattura lo serve al frontend cosi' com'e': i numeri del video
escono da qui, non dalla sceneggiatura.

Ogni parametro porta la sua provenienza. Quelli detti nelle interviste del
golden set (`tests/golden/esaote_ciclo_passivo/sources`) sono `declared`;
volume e costi, che nessuna fonte dice, sono `manual` (assunzione del
consulente). Il To-Be cambia solo cio' che gli intervistati hanno chiesto.

Serve il runner Prosimos (`ops/prosimos/runner`) su PROSIMOS_BASE_URL:

    PYTHONPATH=. uv run python scripts/launch_media_simulate.py
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from backend.simulation.bpmn_normalizer import normalize_bpmn_for_prosimos
from backend.simulation.ir.model import SimulationModel
from backend.simulation.log_processor import activity_name_to_element_id, process_prosimos_log
from backend.simulation.models import ProsimosSimulationRequest
from backend.simulation.prosimos_adapter import run_prosimos_simulation
from backend.simulation.result_parser import with_output_files
from backend.simulation.scenario_builder import baseline_for_bpmn, build_prosimos_scenario_from_model

DATA = Path("e2e/launch-media/data")
SEED = 20261009
TOTAL_CASES = 360
START = "2026-09-07T08:00:00+02:00"

MIN = 60.0
WORKDAY = 8 * 3600.0

SOURCES = {
    "laura": ("source", "src-laura-conti", "Intervista Laura Conti · Ufficio Tecnico"),
    "paolo": ("source", "src-paolo-marchetti", "Intervista Paolo Marchetti · Manutenzione"),
    "francesca": ("source", "src-francesca-neri", "Intervista Francesca Neri · Acquisti"),
}


def declared(*who: str, note: str) -> dict:
    return {
        "origin": "declared",
        "confidence": "medium",
        "sources": [{"kind": SOURCES[w][0], "id": SOURCES[w][1], "label": SOURCES[w][2]} for w in who],
        "note": note,
    }


def assumed(note: str) -> dict:
    return {"origin": "manual", "confidence": "low", "sources": [], "note": note}


def normal(mean_min: float, std_min: float) -> dict:
    mean, std = mean_min * MIN, std_min * MIN
    return {"kind": "normal", "mean": mean, "std": std, "minimum": max(MIN, mean - 3 * std), "maximum": mean + 3 * std}


def lognormal(mean_min: float, std_min: float, cap_min: float) -> dict:
    mean = mean_min * MIN
    return {"kind": "lognormal", "mean": mean, "variance": (std_min * MIN) ** 2, "minimum": MIN, "maximum": cap_min * MIN}


# Tempo di lavoro per attivita' (minuti). Le interviste dicono dove il tempo se
# ne va (ricostruire la richiesta, rimbalzarla, aspettare l'autorizzazione), non
# quanto dura ogni gesto: le durate brevi sono assunzioni, i colli no.
AS_IS_DURATIONS = {
    "rileva_fabbisogno": (normal(10, 3), assumed("Durata del gesto: assunzione del consulente.")),
    "invia_richiesta_ufficio_tecnico": (normal(5, 1), declared("paolo", note="\"Mail. Sempre mail, a Laura.\"")),
    "ricostruisci_richiesta": (
        lognormal(15, 12, 120),
        declared("laura", note="\"Comincia il giro di telefonate. A volte lo risolvo in dieci minuti, a volte ci metto due giorni.\""),
    ),
    "invia_richiesta_acquisti": (normal(5, 1), declared("laura", note="\"La passo ad Acquisti. Gli mando una mail.\"")),
    "verifica_lavorabilita": (normal(10, 3), declared("francesca", note="\"Leggo e verifico se e' lavorabile.\"")),
    "percorso_integrazione_richiedi_integrazione": (
        normal(10, 3),
        declared("francesca", note="\"Rimbalzare indietro le richieste per completarle.\""),
    ),
    "percorso_autorizzazione_richiedi_autorizzazione": (
        normal(5, 1),
        declared("francesca", note="\"E' una mail che mando e una risposta che aspetto.\""),
    ),
    "percorso_autorizzazione_autorizza_spesa": (normal(10, 3), assumed("Durata della firma: assunzione del consulente.")),
    "seleziona_fornitore": (normal(20, 6), declared("francesca", note="\"Per le cose nuove chiedo delle quotazioni in giro e confronto.\"")),
    "emetti_ordine": (normal(10, 3), declared("francesca", note="\"Emetto l'ordine e via.\"")),
    "ricevi_merce": (normal(10, 3), assumed("Durata del gesto: assunzione del consulente.")),
    "verifica_merce": (normal(10, 3), declared("paolo", note="\"Apro la scatola e guardo se e' il pezzo giusto.\"")),
    "percorso_urgente_chiama_fornitore_diretto": (normal(15, 4), declared("paolo", note="\"Chiamo direttamente il fornitore.\"")),
    "percorso_urgente_invia_riferimento_ordine_urgente": (normal(5, 1), declared("paolo", note="\"Mando la mail con il numero di riferimento.\"")),
    "percorso_urgente_regolarizza_ordine": (normal(20, 6), declared("francesca", note="\"La parte di ordine si', la faccio io.\"")),
    "percorso_urgente_gestione_contabile_fattura": (normal(20, 6), declared("francesca", note="\"La parte contabile la fa Amministrazione.\"")),
}

RESOURCES = {
    "Reparto": (4, 38.0),
    "Ufficio Tecnico": (1, 45.0),
    "Ufficio Acquisti": (1, 45.0),
    "Responsabile Acquisti": (1, 70.0),
    "Magazzino": (1, 32.0),
    "Amministrazione": (1, 40.0),
}

# Il responsabile c'e' a tratti e nessuno lo sostituisce (Francesca): le
# autorizzazioni si sbrigano in una finestra breve, il resto del tempo aspettano.
RESPONSABILE_AS_IS = [
    {"from_day": "TUESDAY", "to_day": "TUESDAY", "begin": "16:00:00.000", "end": "17:00:00.000"},
    {"from_day": "THURSDAY", "to_day": "THURSDAY", "begin": "16:00:00.000", "end": "17:00:00.000"},
]

RESPONSABILE_TO_BE = [{"from_day": "MONDAY", "to_day": "FRIDAY", "begin": "16:00:00.000", "end": "17:00:00.000"}]


def as_is_model(base: SimulationModel) -> SimulationModel:
    data = base.model_dump(mode="json")
    data["arrival"]["interarrival"] = {"kind": "exponential", "mean": WORKDAY / 5, "minimum": 0.0, "maximum": WORKDAY}
    data["arrival"]["provenance"] = assumed("Volume: circa 5 richieste al giorno. Nessuna fonte lo dice: assunzione del consulente.")

    data["calendars"].append({"id": "responsabile-assente", "name": "Responsabile presente a tratti", "periods": RESPONSABILE_AS_IS})
    for pool in data["pools"]:
        for resource in pool["resources"]:
            amount, cost = RESOURCES[resource["name"]]
            resource["amount"] = amount
            resource["cost_per_hour"] = cost
            resource["provenance"] = assumed("Persone e costo orario: assunzione del consulente.")
            if resource["name"] == "Responsabile Acquisti":
                resource["calendar_id"] = "responsabile-assente"
                resource["provenance"] = declared(
                    "francesca",
                    note="\"Se e' fuori, possono essere giorni. Non c'e' un sostituto formale.\"",
                )

    for activity in data["activities"]:
        duration, provenance = AS_IS_DURATIONS[activity["element_id"]]
        for assignment in activity["assignments"]:
            assignment["duration"] = duration
            assignment["provenance"] = provenance

    for gateway in data["gateways"]:
        for branch in gateway["branches"]:
            flow = branch["flow_id"]
            if gateway["element_id"] == "urgenza":
                urgent = "percorso_urgente" in flow
                branch["probability"] = 0.03 if urgent else 0.97
                branch["provenance"] = declared("paolo", note="\"Direi qualche volta al mese.\"")
            elif "integrazione" in flow:
                branch["probability"] = 0.55
                branch["provenance"] = declared("francesca", note="\"A sensazione, piu' della meta'.\"")
            elif "autorizzazione" in flow:
                branch["probability"] = 0.15
                branch["provenance"] = assumed("Quota sopra soglia: la soglia e' una lacuna aperta, la quota e' un'assunzione.")
            else:
                branch["probability"] = 0.30
                branch["provenance"] = assumed("Complemento delle altre uscite.")
    return SimulationModel.model_validate(data)


def to_be_model(as_is: SimulationModel) -> SimulationModel:
    """Solo cio' che gli intervistati hanno chiesto, ognuno con la sua citazione."""
    data = as_is.model_dump(mode="json")
    # La richiesta viene dalle interviste, l'effetto stimato no: provenienza
    # manuale, con le fonti che hanno chiesto il cambiamento.
    form = {
        **declared(
            "laura",
            "francesca",
            note="To-Be: \"Farei in modo che la richiesta nasca gia' completa, con i campi obbligatori.\" "
            "Effetto stimato (rimbalzi dal 55% al 25%): assunzione del consulente.",
        ),
        "origin": "manual",
        "confidence": "low",
    }
    for gateway in data["gateways"]:
        if gateway["element_id"] != "esito_verifica":
            continue
        for branch in gateway["branches"]:
            if "integrazione" in branch["flow_id"]:
                # Prudente: il modulo dimezza i rimbalzi, non li azzera.
                branch["probability"] = 0.25
                branch["provenance"] = form
            elif "autorizzazione" in branch["flow_id"]:
                branch["probability"] = 0.15
            else:
                branch["probability"] = 0.60
                branch["provenance"] = form
    for activity in data["activities"]:
        if activity["element_id"] == "ricostruisci_richiesta":
            for assignment in activity["assignments"]:
                assignment["duration"] = normal(8, 3)
                assignment["provenance"] = form
    data["calendars"].append({"id": "responsabile-con-delega", "name": "Autorizzazione ogni giorno (delega)", "periods": RESPONSABILE_TO_BE})
    for pool in data["pools"]:
        for resource in pool["resources"]:
            if resource["name"] == "Responsabile Acquisti":
                # Con la delega la finestra di autorizzazione c'e' ogni giorno,
                # non solo quando il responsabile e' in sede.
                resource["calendar_id"] = "responsabile-con-delega"
                resource["provenance"] = {
                    **declared(
                        "francesca",
                        note="To-Be: \"Vorrei che l'autorizzazione fosse una cosa che si vede.\" "
                        "Delega con una finestra al giorno: assunzione del consulente.",
                    ),
                    "origin": "manual",
                    "confidence": "low",
                }
    return SimulationModel.model_validate(data)


async def run(name: str, bpmn_xml: str, model: SimulationModel) -> dict:
    scenario = build_prosimos_scenario_from_model(bpmn_xml=bpmn_xml, model=model)
    result = with_output_files(
        await run_prosimos_simulation(
            ProsimosSimulationRequest(
                bpmn_xml=bpmn_xml, scenario=scenario, total_cases=TOTAL_CASES, start_date=START, seed=SEED
            )
        )
    )
    if not result.event_log_csv:
        raise RuntimeError(f"{name}: Prosimos non ha restituito il log")
    summary, replay = process_prosimos_log(
        result.event_log_csv,
        normalized_bpmn_xml=bpmn_xml,
        scenario_payload=scenario.payload,
        prosimos_stats=result.payload,
        name_to_element_id=activity_name_to_element_id(bpmn_xml),
    )
    return {
        "name": name,
        "model": model.model_dump(mode="json"),
        "scenario": scenario.payload,
        "result": result.payload,
        "summary": summary,
        "replay": replay,
        "request": {"total_cases": TOTAL_CASES, "start_date": START, "seed": SEED},
    }


async def main() -> None:
    source = (DATA / "as-is.bpmn").read_text(encoding="utf-8")
    bpmn_xml = normalize_bpmn_for_prosimos(source)
    as_is = as_is_model(baseline_for_bpmn(bpmn_xml, source_bpmn_xml=source))
    to_be = to_be_model(as_is)
    runs = {
        "as_is": await run("As-Is v3 · validato", bpmn_xml, as_is),
        "to_be": await run("To-Be · richiesta completa + delega", bpmn_xml, to_be),
    }
    (DATA / "runs.json").write_text(json.dumps(runs, ensure_ascii=False), encoding="utf-8")
    for key, value in runs.items():
        s = value["summary"]
        print(
            key,
            f"casi={s['casesCompleted']}",
            f"ciclo_medio_gg={s['cycle']['avg'] / 86400:.2f}",
            f"p90_gg={s['cycle']['p90'] / 86400:.2f}",
            f"attesa={s['waiting']['share']:.0%}",
            f"costo_caso={s['cost']['perCase']:.2f}",
            f"collo={s.get('bottleneck', {}).get('name') if s.get('bottleneck') else None}",
        )


if __name__ == "__main__":
    asyncio.run(main())
