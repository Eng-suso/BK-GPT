"""I due tool con cui il Canvas parla alla knowledge authority del processo.

Il Canvas Agent non e' un consumatore passivo di un payload: durante il run
decide da solo quando ha bisogno di rileggere cio' che il processo sa
(`inspect_process_knowledge`) e quando invece ha trovato una cosa che non puo'
decidere da solo (`raise_modeling_question`).

La regola che rende agentico questo senza creare una seconda verita' e' una
sola: **il Canvas puo' leggere e puo' chiedere, non puo' concludere**. Una
domanda non e' una risposta provvisoria da tenersi in tasca: e' un record che
rientra nel Process IR, fa salire la versione dello snapshot, e torna al Canvas
come conoscenza autorevole solo dopo che qualcuno ha risposto.
"""

from __future__ import annotations

import json
from typing import Literal

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from backend.agents.process_snapshot import (
    build_process_snapshot,
    render_snapshot_for_modeling,
)
from backend.process_understanding import (
    ProcessUnderstanding,
    ProcessUnknown,
    ProcessUnknownOption,
)
from backend.toolsets.workspace import enterprise_tool_result


class ModelingQuestionOptionInput(BaseModel):
    label: str = Field(description="Short, pickable answer - a few words, not a sentence.")
    implication: str = Field(
        default="",
        description="What changes in the BPMN model if this answer is the right one.",
    )


class ModelingQuestionInput(BaseModel):
    process_id: str = Field(description="Current process id.")
    question: str = Field(
        description=(
            "The single modeling decision you cannot make from the snapshot. Name the "
            "concrete element, path or actor, not a category."
        )
    )
    affects: str = Field(
        description="Which part of the BPMN model this blocks: a gateway, a lane, an exception path."
    )
    grounded_in: str = Field(
        description=(
            "The gap in the recorded evidence that makes this question necessary: name "
            "the voice and what it said. A question the sources never touched is not a "
            "modeling gap, and the runtime will drop it."
        )
    )
    options: list[ModelingQuestionOptionInput] = Field(
        default_factory=list,
        description="Two to four modeling alternatives the evidence makes possible.",
    )
    severity: Literal["blocking", "non_blocking", "optional_extension"] = Field(
        default="blocking",
        description=(
            "blocking only when the topology cannot be drawn at all without the answer. "
            "If you can draw it and flag the uncertainty, it is non_blocking."
        ),
    )


@tool
def inspect_process_knowledge(process_id: str) -> str:
    """
    Read the authoritative, versioned knowledge snapshot of one process: recorded
    sources, claims with who states them and how well supported they are, open
    gaps with their alternatives, decisions already taken, readiness and the
    canonical ProcessUnderstanding/BPMNSemanticModel.

    This is the only knowledge the Canvas may model from. Call it before building
    or rebuilding a diagram, and again whenever a modeling decision depends on
    something you are not sure the snapshot contains. Do not reconstruct the
    process from chat prose.
    """
    snapshot = build_process_snapshot(process_id)
    if snapshot is None:
        raise ValueError(f"Processo non trovato: {process_id}")

    warnings: list[str] = []
    if not snapshot.has_semantic_model:
        warnings.append(
            "Nessun modello semantico canonico: il processo non ha ancora un piano "
            "approvabile. Il Canvas non puo' costruirlo da solo."
        )
    if snapshot.source_status in {"error", "stale"}:
        warnings.append("Il set di fonti non e' stato riletto in questo turno.")
    if snapshot.claim_status not in {"ok", "empty"}:
        warnings.append("La proiezione dei claim e' incompleta: la provenance puo' essere parziale.")
    warnings.extend(
        f"Lacuna bloccante aperta: {item.question}" for item in snapshot.blocking_questions
    )

    return enterprise_tool_result(
        status="ok" if snapshot.has_semantic_model else "missing_semantic_model",
        action="inspect_process_knowledge",
        entity_type="process_knowledge_snapshot",
        entity_id=process_id,
        summary=(
            f"Snapshot {snapshot.label} di {snapshot.process_name}: "
            f"{len(snapshot.sources)} fonti, {len(snapshot.claims)} affermazioni, "
            f"{len([q for q in snapshot.open_questions if not q.answer])} lacune aperte."
        ),
        payload={
            **snapshot.as_handoff_payload(),
            "knowledge_brief": render_snapshot_for_modeling(snapshot),
            "process_understanding": snapshot.process_understanding,
            "bpmn_semantic_model": snapshot.bpmn_semantic_model,
            "open_questions": [item.model_dump(mode="json") for item in snapshot.open_questions],
            "missing_information": snapshot.missing_information,
            "draft_readiness": snapshot.draft_readiness,
            "validation_readiness": snapshot.validation_readiness,
            "ledger_summary": snapshot.ledger_summary,
        },
        warnings=warnings,
    )


@tool(args_schema=ModelingQuestionInput)
def raise_modeling_question(
    process_id: str,
    question: str,
    affects: str,
    grounded_in: str,
    options: list[ModelingQuestionOptionInput] | None = None,
    severity: str = "blocking",
) -> str:
    """
    Hand one modeling decision back to the process knowledge owner instead of
    guessing it. Use when the snapshot genuinely does not settle how the diagram
    must be drawn: which branch a gateway takes, who owns a lane, whether an
    exception is a boundary event or a separate path.

    The question is recorded against the authoritative process plan, not kept on
    the canvas: it raises the snapshot version, reaches the consultant as an open
    question with your alternatives, and comes back to you as knowledge once it
    is answered. It does not answer itself, and it does not modify the diagram.

    A question the recorded sources never touched is not a modeling gap: the
    runtime drops it and tells you so. Re-read the snapshot instead.
    """
    from backend import workspace_database
    from backend.agents.scope_guard import assert_process_in_scope

    assert_process_in_scope(process_id)

    snapshot = build_process_snapshot(process_id)
    if snapshot is None:
        raise ValueError(f"Processo non trovato: {process_id}")
    if not snapshot.process_understanding:
        raise ValueError(
            "Questo processo non ha ancora un piano su cui registrare una domanda. "
            "Il lavoro che manca e' la comprensione del processo, non il disegno."
        )

    clean_question = " ".join(str(question or "").split())
    if not clean_question:
        raise ValueError("La domanda di modellazione non puo' essere vuota.")

    understanding = ProcessUnderstanding.model_validate(snapshot.process_understanding)
    already_asked = any(
        item.question_id == ProcessUnknown(question=clean_question, affects=affects).question_id
        for item in understanding.unknowns
    )
    if already_asked:
        # Ripresentare la stessa domanda non e' un progresso: la versione non
        # deve salire, e il Canvas deve sapere che sta aspettando, non chiedendo.
        return enterprise_tool_result(
            status="already_open",
            action="raise_modeling_question",
            entity_type="process_modeling_question",
            entity_id=process_id,
            summary=f"La domanda e' gia' aperta sul piano {snapshot.label}.",
            payload={**snapshot.as_handoff_payload(), "question": clean_question},
            warnings=["Stai aspettando questa risposta: non riproporla, e non modellarla da solo."],
        )

    understanding.unknowns = [
        *understanding.unknowns,
        ProcessUnknown(
            question=clean_question,
            affects=affects,
            severity=severity,
            grounded_in=grounded_in,
            options=[
                ProcessUnknownOption(label=option.label, implication=option.implication)
                for option in options or []
            ],
        ),
    ]

    review = workspace_database.revise_bpmn_review(
        bpmn_model_id=snapshot.bpmn_model_id,
        process_understanding=understanding.model_dump(mode="json"),
        change_summary=f"Domanda di modellazione dal canvas: {clean_question}",
    )
    updated = build_process_snapshot(process_id)
    recorded = any(
        " ".join(str(item.get("question") or "").split()) == clean_question
        for item in review.get("open_questions") or []
    )

    if not recorded:
        # Il filtro di ancoraggio l'ha scartata: la domanda non citava una lacuna
        # di questo processo. Non e' un fallimento tecnico, e' la stessa regola
        # che impedisce al piano di richiedere cio' che le fonti hanno gia' detto.
        return enterprise_tool_result(
            status="dropped_not_grounded",
            action="raise_modeling_question",
            entity_type="process_modeling_question",
            entity_id=process_id,
            summary="Domanda scartata: non cita una lacuna dell'evidenza di questo processo.",
            payload={
                **(updated.as_handoff_payload() if updated else {}),
                "question": clean_question,
                "grounded_in": grounded_in,
            },
            warnings=[
                "Rileggi lo snapshot con inspect_process_knowledge e riformula partendo "
                "da cio' che una fonte ha effettivamente detto, oppure modella "
                "l'incertezza invece di richiederla."
            ],
            next_actions=[
                {"owner": "canvas_construction_agent", "action": "inspect_process_knowledge"}
            ],
        )

    return enterprise_tool_result(
        status="waiting_for_user",
        action="raise_modeling_question",
        entity_type="process_modeling_question",
        entity_id=process_id,
        summary=f"Domanda registrata sul piano: {clean_question}",
        payload={
            **(updated.as_handoff_payload() if updated else {}),
            "question": clean_question,
            "affects": affects,
            "severity": severity,
            "options": [option.model_dump() for option in options or []],
            "previous_snapshot_id": snapshot.snapshot_id,
            "previous_snapshot_label": snapshot.label,
        },
        warnings=[
            "Il piano e' cambiato: lo snapshot su cui stavi lavorando non e' piu' "
            "l'ultimo. Non applicare un disegno costruito sulla versione precedente."
        ],
        next_actions=[
            {
                "owner": "user_or_consultant",
                "action": "answer_modeling_question",
                "question": clean_question,
            }
        ],
    )


def modeling_question_payload(tool_output: str) -> dict:
    """Il payload di un risultato di `raise_modeling_question`, per il runtime.

    I tool tornano una riga di titolo e poi il JSON: qui si legge la seconda
    parte senza far ripassare il documento dal modello.
    """
    try:
        return json.loads(tool_output.split("\n", 1)[1])
    except (IndexError, json.JSONDecodeError):
        return {}


process_knowledge_tools = [
    inspect_process_knowledge,
    raise_modeling_question,
]
