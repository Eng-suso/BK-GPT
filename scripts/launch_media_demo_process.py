"""Il processo demo dei video: "Gestione richiesta di acquisto" di Vetrano Industriale.

Versione rivista su OMG BPMN 2.0.2 (revisione di Sohayb, 13 ottobre 2026):

- la pool e' il partecipante (Vetrano Industriale S.p.A.), il processo ha il suo
  nome, le corsie sono i ruoli;
- il processo parte da un evento condizionale ("Fabbisogno di acquisto rilevato");
- la richiesta incompleta passa da "Richiedi integrazione" (Acquisti) prima di
  "Integra la richiesta" (Reparto) e rientra direttamente in "Verifica la
  completezza": i due ingressi sono alternativi, quindi niente rombo di merge
  (OMG 10.5.2). Nel diagramma i rombi sono solo i punti in cui il processo decide;
- "Valuta la richiesta di spesa" e' un'azione, "Spesa autorizzata?" la
  decisione: il rifiuto ha il suo ramo e la sua fine;
- ogni gateway esclusivo ha una condizione sul "Sì" e il "No" come default;
- "Richiesta di acquisto" e "Ordine di acquisto" sono data object, collegati
  all'attivita' che li produce (nel video le letture renderebbero il disegno
  illeggibile; OMG non obbliga a disegnarle tutte).

Il fornitore e' fuori scope (il processo interno finisce con l'ordine emesso).

Pipeline del prodotto: ProcessUnderstanding -> compilatore -> validazione ->
layout enterprise -> lint visivo -> schema XSD ufficiale OMG BPMN 2.0.
Esce `e2e/launch-media/data/demo.bpmn` e, in inglese per il sito, `demo.en.bpmn`.

    PYTHONPATH=. uv run python scripts/launch_media_demo_process.py
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from lxml import etree

from backend.bpmn import build_bpmn_semantic_model
from backend.bpmn.canvas_layout import apply_enterprise_layout, lint_visual_model
from backend.bpmn.soundness import analyze_control_flow
from backend.bpmn.validation import validate_bpmn_semantic_model
from backend.process_understanding import (
    ProcessActor,
    ProcessBoundaries,
    ProcessDataObject,
    ProcessDecision,
    ProcessDecisionOutcome,
    ProcessEvent,
    ProcessFlowEdge,
    ProcessPath,
    ProcessStep,
    ProcessUnderstanding,
)

OUT = Path("e2e/launch-media/data/demo.bpmn")
# Lo schema ufficiale OMG BPMN 2.0 (BPMN20.xsd e gli import DI/DC), da bpmn-moddle.
OMG_XSD = Path("frontend/node_modules/bpmn-moddle/resources/bpmn/xsd/BPMN20.xsd")
BPMN = "http://www.omg.org/spec/BPMN/20100524/MODEL"

PROCESS_ID = "Process_richiesta_acquisto"
PARTICIPANT = "Vetrano Industriale S.p.A."
REPARTO, ACQUISTI, RESPONSABILE = "Actor_Reparto", "Actor_Acquisti", "Actor_Responsabile"

# Il sito e' in italiano e in inglese: stesso processo, stessi id, testi tradotti.
# In inglese le attivita' sono corte (verbo + oggetto): su due righe la prima
# finirebbe sotto l'icona del compito, che bpmn-js non scansa.
TEXT = {
    "it": {
        "process": "Gestione richiesta di acquisto",
        "objective": "Dal fabbisogno all'ordine di acquisto emesso",
        "Actor_Reparto": "Reparto richiedente",
        "Actor_Acquisti": "Ufficio Acquisti",
        "Actor_Responsabile": "Responsabile Acquisti",
        "Event_Start": "Fabbisogno di acquisto rilevato",
        "start_condition": "esiste un fabbisogno di acquisto",
        "Event_Emesso": "Ordine emesso",
        "Event_Respinta": "Richiesta respinta",
        "Task_Compila": "Compila la richiesta di acquisto",
        "Task_Invia": "Invia la richiesta",
        "Task_Verifica": "Verifica la completezza della richiesta",
        "Task_Richiedi": "Richiedi integrazione",
        "Task_Integra": "Integra la richiesta",
        "Task_Valuta": "Valuta la richiesta di spesa",
        "Task_Rifiuto": "Comunica il rifiuto",
        "Task_Emetti": "Emetti l'ordine di acquisto",
        "Data_Richiesta": "Richiesta di acquisto",
        "Data_Ordine": "Ordine di acquisto",
        "Decision_Completa": "Richiesta completa?",
        "Decision_Necessaria": "Autorizzazione necessaria?",
        "Decision_Autorizzata": "Spesa autorizzata?",
        "yes": "Sì",
        "no": "No",
        "completa": "richiesta completa",
        "soglia": "importo sopra la soglia di autorizzazione (soglia da chiarire)",
        "autorizzata": "spesa autorizzata",
        "Path_Integrazione": "Richiesta incompleta",
        "Path_Senza_Autorizzazione": "Sotto soglia",
        "Path_Rifiuto": "Spesa non autorizzata",
    },
    "en": {
        "process": "Purchase request handling",
        "objective": "From the purchasing need to the issued purchase order",
        "Actor_Reparto": "Requesting department",
        "Actor_Acquisti": "Purchasing Office",
        "Actor_Responsabile": "Purchasing Manager",
        "Event_Start": "Purchasing need identified",
        "start_condition": "a purchasing need exists",
        "Event_Emesso": "Order issued",
        "Event_Respinta": "Request rejected",
        "Task_Compila": "Fill in the request",
        "Task_Invia": "Send the request",
        "Task_Verifica": "Check the request is complete",
        "Task_Richiedi": "Ask for missing details",
        "Task_Integra": "Complete the request",
        "Task_Valuta": "Assess the spend",
        "Task_Rifiuto": "Send the rejection",
        "Task_Emetti": "Issue the order",
        "Data_Richiesta": "Purchase request",
        "Data_Ordine": "Purchase order",
        "Decision_Completa": "Request complete?",
        "Decision_Necessaria": "Authorization required?",
        "Decision_Autorizzata": "Spending authorized?",
        "yes": "Yes",
        "no": "No",
        "completa": "request complete",
        "soglia": "amount above the authorization threshold (threshold to be clarified)",
        "autorizzata": "spending authorized",
        "Path_Integrazione": "Incomplete request",
        "Path_Senza_Autorizzazione": "Below threshold",
        "Path_Rifiuto": "Spending not authorized",
    },
}
OUT_BY_LANG = {"it": OUT, "en": OUT.with_name("demo.en.bpmn")}


def understanding(lang: str = "it") -> ProcessUnderstanding:
    t = TEXT[lang]

    def step(step_id: str, label: str, actor: str, **extra) -> ProcessStep:
        return ProcessStep(id=step_id, label=label, actor_ids=[actor], type="user_task", **extra)

    main = ["Task_Compila", "Task_Invia", "Task_Verifica", "Task_Valuta", "Task_Emetti"]
    return ProcessUnderstanding(
        title=t["process"],
        objective=t["objective"],
        actors=[
            ProcessActor(id=REPARTO, label=t[REPARTO], kind="team"),
            ProcessActor(id=ACQUISTI, label=t[ACQUISTI], kind="team"),
            ProcessActor(id=RESPONSABILE, label=t[RESPONSABILE], kind="role"),
        ],
        events=[
            ProcessEvent(
                id="Event_Start", label=t["Event_Start"], type="start",
                definition="conditional", condition=t["start_condition"],
            ),
            ProcessEvent(id="Event_Emesso", label=t["Event_Emesso"], type="end"),
            ProcessEvent(id="Event_Respinta", label=t["Event_Respinta"], type="end"),
        ],
        steps=[
            step("Task_Compila", t["Task_Compila"], REPARTO, outputs=[t["Data_Richiesta"]]),
            step("Task_Invia", t["Task_Invia"], REPARTO),
            step("Task_Verifica", t["Task_Verifica"], ACQUISTI),
            step("Task_Richiedi", t["Task_Richiedi"], ACQUISTI),
            step("Task_Integra", t["Task_Integra"], REPARTO),
            step("Task_Valuta", t["Task_Valuta"], RESPONSABILE),
            step("Task_Rifiuto", t["Task_Rifiuto"], RESPONSABILE),
            step("Task_Emetti", t["Task_Emetti"], ACQUISTI, outputs=[t["Data_Ordine"]]),
        ],
        data_objects=[
            ProcessDataObject(id="Data_Richiesta", label=t["Data_Richiesta"], kind="document"),
            ProcessDataObject(id="Data_Ordine", label=t["Data_Ordine"], kind="document"),
        ],
        sequence=main,
        main_success_path=main,
        boundaries=ProcessBoundaries(
            start_event=t["Event_Start"],
            success_end=t["Event_Emesso"],
            failure_ends=[t["Event_Respinta"]],
        ),
        decisions=[
            ProcessDecision(
                id="Decision_Completa",
                label=t["Decision_Completa"],
                question=t["Decision_Completa"],
                outcomes=[t["yes"], t["no"]],
                outcome_details=[
                    ProcessDecisionOutcome(id="Completa_Si", label=t["yes"], condition=t["completa"], target_ref="Decision_Necessaria"),
                    ProcessDecisionOutcome(id="Completa_No", label=t["no"], target_path_id="Path_Integrazione", is_default=True),
                ],
            ),
            # Francesca: «Sopra una certa cifra devo chiedere una autorizzazione al
            # mio responsabile.» Non tutte le richieste passano dal responsabile;
            # la soglia nessuno la dice, quindi la condizione la nomina senza un numero.
            ProcessDecision(
                id="Decision_Necessaria",
                label=t["Decision_Necessaria"],
                question=t["Decision_Necessaria"],
                outcomes=[t["yes"], t["no"]],
                outcome_details=[
                    ProcessDecisionOutcome(
                        id="Necessaria_Si", label=t["yes"], condition=t["soglia"],
                        target_ref="Task_Valuta",
                    ),
                    ProcessDecisionOutcome(id="Necessaria_No", label=t["no"], target_path_id="Path_Senza_Autorizzazione", is_default=True),
                ],
            ),
            ProcessDecision(
                id="Decision_Autorizzata",
                label=t["Decision_Autorizzata"],
                question=t["Decision_Autorizzata"],
                outcomes=[t["yes"], t["no"]],
                outcome_details=[
                    ProcessDecisionOutcome(id="Autorizzata_Si", label=t["yes"], condition=t["autorizzata"], target_ref="Task_Emetti"),
                    ProcessDecisionOutcome(id="Autorizzata_No", label=t["no"], target_path_id="Path_Rifiuto", is_default=True, ends_process=True),
                ],
            ),
        ],
        flow_edges=[
            ProcessFlowEdge(id="Edge_Verifica", source_id="Task_Verifica", target_id="Decision_Completa", label=""),
            ProcessFlowEdge(id="Edge_Completa", source_id="Decision_Completa", target_id="Decision_Necessaria", label=t["yes"]),
            ProcessFlowEdge(id="Edge_Valuta", source_id="Task_Valuta", target_id="Decision_Autorizzata", label=""),
        ],
        alternative_paths=[
            ProcessPath(
                id="Path_Integrazione", label=t["Path_Integrazione"],
                sequence=["Task_Richiedi", "Task_Integra"], rejoins_at="Task_Verifica",
            ),
            # Sotto soglia si ordina subito: un ramo senza attivita' che rientra su "Emetti".
            ProcessPath(
                id="Path_Senza_Autorizzazione", label=t["Path_Senza_Autorizzazione"],
                sequence=[], rejoins_at="Task_Emetti",
            ),
            ProcessPath(
                id="Path_Rifiuto", label=t["Path_Rifiuto"],
                sequence=["Task_Rifiuto"], ends_at=t["Event_Respinta"],
            ),
        ],
    )


def build(lang: str) -> list[str]:
    process_name = TEXT[lang]["process"]
    model = build_bpmn_semantic_model(process_id=PROCESS_ID, process_name=process_name, process=understanding(lang))
    problems = [*model.model_warnings, *validate_bpmn_semantic_model(model)]
    soundness = analyze_control_flow(model)
    problems += [f"{issue.code}: {issue.message}" for issue in [*soundness.errors, *soundness.warnings]]
    xml = apply_enterprise_layout(model, process_name=process_name)
    root = ET.fromstring(xml)
    # Una sola pool: il partecipante e' il cliente, il processo resta col suo nome.
    for participant in root.iter(f"{{{BPMN}}}participant"):
        participant.set("name", PARTICIPANT)
    xml = ET.tostring(root, encoding="unicode", xml_declaration=True)
    # Per la demo anche gli avvisi bloccano: nessun incrocio tra flussi.
    lint = lint_visual_model(ET.fromstring(xml))
    problems += [*lint["issues"], *lint["warnings"]]
    schema = etree.XMLSchema(etree.parse(str(OMG_XSD)))
    if not schema.validate(etree.fromstring(xml.encode())):
        problems += [f"XSD OMG riga {e.line}: {e.message}" for e in schema.error_log]
    problems = [f"[{lang}] {line}" for line in problems]
    if not problems:
        OUT_BY_LANG[lang].write_text(xml, encoding="utf-8")
        print(f"ok {OUT_BY_LANG[lang]}: {len(model.flowNodes)} nodi, {len(model.dataObjects)} data object")
    return problems


def main() -> int:
    problems = [line for lang in TEXT for line in build(lang)]
    for line in problems:
        print("!", line)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
