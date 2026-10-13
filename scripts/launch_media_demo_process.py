"""Il processo demo unico dei video: "Richiesta d'acquisto" di Vetrano Industriale.

Il piano video (docs/launch/video-plan-review.md) vuole un solo processo piccolo
per tutte le scene: 2 pool, la prima divisa in 2 corsie, una decisione con il
suo ritorno. Il modello esce dalla pipeline del prodotto, non da un disegno a
mano: ProcessUnderstanding -> compilatore -> validazione -> layout enterprise
-> lint visivo -> schema XSD ufficiale OMG BPMN 2.0.

Il Fornitore e' una pool chiusa: le sue attivita' non si vedono, si vedono i
messaggi (ordine in uscita, conferma e merce in entrata).

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
    BpmnLaneCandidate,
    BpmnMessageFlowCandidate,
    BpmnParticipantTopology,
    BpmnPoolCandidate,
    ProcessActor,
    ProcessBoundaries,
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
PROCESS_ID = "Process_richiesta_acquisto"
PROCESS_NAME = "Richiesta d'acquisto"

REPARTO, ACQUISTI, FORNITORE = "Actor_Reparto", "Actor_Acquisti", "Actor_Fornitore"


def understanding() -> ProcessUnderstanding:
    steps = [
        ProcessStep(id="Task_Compila", label="Compila la richiesta d'acquisto", actor_ids=[REPARTO], type="user_task"),
        ProcessStep(id="Task_Verifica", label="Verifica la completezza", actor_ids=[ACQUISTI], type="user_task"),
        ProcessStep(id="Task_Integra", label="Integra la richiesta", actor_ids=[REPARTO], type="user_task"),
        ProcessStep(id="Task_Autorizza", label="Autorizza la spesa", actor_ids=[ACQUISTI], type="user_task"),
        ProcessStep(id="Task_Emetti", label="Emetti l'ordine", actor_ids=[ACQUISTI], type="send_task"),
        ProcessStep(id="Task_Ricevi", label="Ricevi la merce", actor_ids=[ACQUISTI], type="receive_task"),
    ]
    main = ["Task_Compila", "Task_Verifica", "Task_Autorizza", "Task_Emetti", "Task_Ricevi"]
    return ProcessUnderstanding(
        title=PROCESS_NAME,
        objective="Dal materiale mancante all'ordine al fornitore",
        actors=[
            ProcessActor(id=REPARTO, label="Reparto richiedente", kind="team"),
            ProcessActor(id=ACQUISTI, label="Ufficio Acquisti", kind="team"),
            ProcessActor(id=FORNITORE, label="Fornitore", kind="external_party"),
        ],
        events=[
            ProcessEvent(id="Event_Start", label="Materiale mancante", type="start"),
            ProcessEvent(id="Event_End", label="Merce ricevuta", type="end"),
        ],
        steps=steps,
        sequence=main,
        main_success_path=main,
        boundaries=ProcessBoundaries(start_event="Materiale mancante", success_end="Merce ricevuta"),
        decisions=[
            ProcessDecision(
                id="Decision_Completa",
                label="Richiesta completa?",
                question="Richiesta completa?",
                outcomes=["Sì", "No"],
                outcome_details=[
                    ProcessDecisionOutcome(id="Out_Si", label="Sì", target_ref="Task_Autorizza", is_default=True),
                    ProcessDecisionOutcome(id="Out_No", label="No", condition="mancano dati", target_path_id="Path_Integra"),
                ],
            )
        ],
        flow_edges=[
            ProcessFlowEdge(id="Edge_Verifica", source_id="Task_Verifica", target_id="Decision_Completa", label=""),
        ],
        alternative_paths=[
            ProcessPath(
                id="Path_Integra",
                label="Richiesta incompleta",
                sequence=["Task_Integra"],
                rejoins_at="Task_Verifica",
            )
        ],
        bpmn_topology=BpmnParticipantTopology(
            pools=[
                BpmnPoolCandidate(
                    id="Pool_Vetrano", label="Vetrano – Acquisti", participant_id="Participant_Vetrano",
                    actor_ids=[REPARTO, ACQUISTI],
                ),
                BpmnPoolCandidate(
                    id="Pool_Fornitore", label="Fornitore", participant_id="Participant_Fornitore",
                    actor_ids=[FORNITORE], is_external=True, rendering_intent="black_box",
                ),
            ],
            lanes=[
                BpmnLaneCandidate(id="Lane_Reparto", label="Reparto richiedente", pool_id="Pool_Vetrano", actor_ids=[REPARTO]),
                BpmnLaneCandidate(id="Lane_Acquisti", label="Ufficio Acquisti", pool_id="Pool_Vetrano", actor_ids=[ACQUISTI]),
            ],
            message_flows=[
                BpmnMessageFlowCandidate(
                    id="Message_Ordine", label="Ordine", from_participant_id="Participant_Vetrano",
                    to_participant_id="Participant_Fornitore", source_ref="Task_Emetti", artifact="Ordine d'acquisto",
                ),
                BpmnMessageFlowCandidate(
                    id="Message_Merce", label="Merce e conferma di consegna", from_participant_id="Participant_Fornitore",
                    to_participant_id="Participant_Vetrano", target_ref="Task_Ricevi",
                ),
            ],
            black_box_participant_ids=["Participant_Fornitore"],
        ),
    )


def main() -> int:
    model = build_bpmn_semantic_model(process_id=PROCESS_ID, process_name=PROCESS_NAME, process=understanding())
    problems = validate_bpmn_semantic_model(model)
    soundness = analyze_control_flow(model)
    xml = apply_enterprise_layout(model, process_name=PROCESS_NAME)
    lint = lint_visual_model(ET.fromstring(xml))
    schema = etree.XMLSchema(etree.parse(str(OMG_XSD)))
    if not schema.validate(etree.fromstring(xml.encode())):
        problems = [*problems, *(f"XSD OMG riga {e.line}: {e.message}" for e in schema.error_log)]
    for line in [*model.model_warnings, *problems, *(f"{i.code}: {i.message}" for i in soundness.errors), *lint["issues"]]:
        print("!", line)
    if problems or soundness.warnings or not soundness.is_sound or not lint["valid"]:
        return 1
    OUT.write_text(xml)
    print(f"ok {OUT}: {len(model.flowNodes)} nodi, {len(model.sequenceFlows)} flussi, {len(model.messageFlows)} messaggi")
    return 0


if __name__ == "__main__":
    sys.exit(main())
