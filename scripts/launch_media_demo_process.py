"""Il processo demo dei video: "Gestione richiesta di acquisto" di Vetrano Industriale.

Versione rivista su OMG BPMN 2.0.2 (revisione di Sohayb, 13 ottobre 2026):

- la pool e' il partecipante (Vetrano Industriale S.p.A.), il processo ha il suo
  nome, le corsie sono i ruoli;
- il processo parte da un evento condizionale ("Fabbisogno di acquisto rilevato");
- la richiesta incompleta passa da "Richiedi integrazione" (Acquisti) prima di
  "Integra la richiesta" (Reparto) e rientra da un merge esplicito;
- "Valuta l'autorizzazione della spesa" e' un'azione, "Spesa autorizzata?" la
  decisione: il rifiuto ha il suo ramo e la sua fine;
- ogni gateway esclusivo ha una condizione sul "Sì" e il "No" come default;
- "Richiesta di acquisto" e "Ordine di acquisto" sono data object.

Il fornitore e' fuori scope (il processo interno finisce con l'ordine emesso).

Pipeline del prodotto: ProcessUnderstanding -> compilatore -> validazione ->
layout enterprise -> lint visivo -> schema XSD ufficiale OMG BPMN 2.0.
Esce `e2e/launch-media/data/demo.bpmn`.

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
PROCESS_NAME = "Gestione richiesta di acquisto"
PARTICIPANT = "Vetrano Industriale S.p.A."
REPARTO, ACQUISTI, RESPONSABILE = "Actor_Reparto", "Actor_Acquisti", "Actor_Responsabile"
RICHIESTA, ORDINE = "Richiesta di acquisto", "Ordine di acquisto"


def understanding() -> ProcessUnderstanding:
    def step(step_id: str, label: str, actor: str, **extra) -> ProcessStep:
        return ProcessStep(id=step_id, label=label, actor_ids=[actor], type="user_task", **extra)

    main = ["Task_Compila", "Task_Invia", "Task_Verifica", "Task_Valuta", "Task_Emetti"]
    return ProcessUnderstanding(
        title=PROCESS_NAME,
        objective="Dal fabbisogno all'ordine di acquisto emesso",
        actors=[
            ProcessActor(id=REPARTO, label="Reparto richiedente", kind="team"),
            ProcessActor(id=ACQUISTI, label="Ufficio Acquisti", kind="team"),
            ProcessActor(id=RESPONSABILE, label="Responsabile Acquisti", kind="role"),
        ],
        events=[
            ProcessEvent(
                id="Event_Start", label="Fabbisogno di acquisto rilevato", type="start",
                definition="conditional", condition="esiste un fabbisogno di acquisto",
            ),
            ProcessEvent(id="Event_Emesso", label="Ordine emesso", type="end"),
            ProcessEvent(id="Event_Respinta", label="Richiesta respinta", type="end"),
        ],
        steps=[
            step("Task_Compila", "Compila la richiesta di acquisto", REPARTO, outputs=[RICHIESTA]),
            step("Task_Invia", "Invia la richiesta", REPARTO, inputs=[RICHIESTA]),
            step("Task_Verifica", "Verifica la completezza della richiesta", ACQUISTI, inputs=[RICHIESTA]),
            step("Task_Richiedi", "Richiedi integrazione", ACQUISTI),
            step("Task_Integra", "Integra la richiesta", REPARTO, outputs=[RICHIESTA]),
            step("Task_Valuta", "Valuta l'autorizzazione della spesa", RESPONSABILE, inputs=[RICHIESTA]),
            step("Task_Rifiuto", "Comunica il rifiuto", RESPONSABILE),
            step("Task_Emetti", "Emetti l'ordine di acquisto", ACQUISTI, outputs=[ORDINE]),
        ],
        data_objects=[
            ProcessDataObject(id="Data_Richiesta", label=RICHIESTA, kind="document"),
            ProcessDataObject(id="Data_Ordine", label=ORDINE, kind="document"),
        ],
        sequence=main,
        main_success_path=main,
        boundaries=ProcessBoundaries(
            start_event="Fabbisogno di acquisto rilevato",
            success_end="Ordine emesso",
            failure_ends=["Richiesta respinta"],
        ),
        decisions=[
            ProcessDecision(
                id="Decision_Completa",
                label="Richiesta completa?",
                question="Richiesta completa?",
                outcomes=["Sì", "No"],
                outcome_details=[
                    ProcessDecisionOutcome(id="Completa_Si", label="Sì", condition="richiesta completa", target_ref="Task_Valuta"),
                    ProcessDecisionOutcome(id="Completa_No", label="No", target_path_id="Path_Integrazione", is_default=True),
                ],
            ),
            ProcessDecision(
                id="Decision_Autorizzata",
                label="Spesa autorizzata?",
                question="Spesa autorizzata?",
                outcomes=["Sì", "No"],
                outcome_details=[
                    ProcessDecisionOutcome(id="Autorizzata_Si", label="Sì", condition="spesa autorizzata", target_ref="Task_Emetti"),
                    ProcessDecisionOutcome(id="Autorizzata_No", label="No", target_path_id="Path_Rifiuto", is_default=True, ends_process=True),
                ],
            ),
        ],
        flow_edges=[
            ProcessFlowEdge(id="Edge_Verifica", source_id="Task_Verifica", target_id="Decision_Completa", label=""),
            ProcessFlowEdge(id="Edge_Valuta", source_id="Task_Valuta", target_id="Decision_Autorizzata", label=""),
        ],
        alternative_paths=[
            ProcessPath(
                id="Path_Integrazione", label="Richiesta incompleta",
                sequence=["Task_Richiedi", "Task_Integra"], rejoins_at="Task_Verifica",
            ),
            ProcessPath(
                id="Path_Rifiuto", label="Spesa non autorizzata",
                sequence=["Task_Rifiuto"], ends_at="Richiesta respinta",
            ),
        ],
    )


def main() -> int:
    model = build_bpmn_semantic_model(process_id=PROCESS_ID, process_name=PROCESS_NAME, process=understanding())
    problems = [*model.model_warnings, *validate_bpmn_semantic_model(model)]
    soundness = analyze_control_flow(model)
    problems += [f"{issue.code}: {issue.message}" for issue in [*soundness.errors, *soundness.warnings]]
    xml = apply_enterprise_layout(model, process_name=PROCESS_NAME)
    root = ET.fromstring(xml)
    # Una sola pool: il partecipante e' il cliente, il processo resta col suo nome.
    for participant in root.iter(f"{{{BPMN}}}participant"):
        participant.set("name", PARTICIPANT)
    xml = ET.tostring(root, encoding="unicode", xml_declaration=True)
    problems += lint_visual_model(ET.fromstring(xml))["issues"]
    schema = etree.XMLSchema(etree.parse(str(OMG_XSD)))
    if not schema.validate(etree.fromstring(xml.encode())):
        problems += [f"XSD OMG riga {e.line}: {e.message}" for e in schema.error_log]
    for line in problems:
        print("!", line)
    if problems:
        return 1
    OUT.write_text(xml, encoding="utf-8")
    print(f"ok {OUT}: {len(model.flowNodes)} nodi, {len(model.dataObjects)} data object")
    return 0


if __name__ == "__main__":
    sys.exit(main())
