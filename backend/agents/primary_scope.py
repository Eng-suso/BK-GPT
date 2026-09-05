from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel

from backend.schemas.chat import DEFAULT_CHAT_MODE, ChatMode, ChatScope, chat_scope_key


AgentScopeType = Literal["consultant", "project", "process", "canvas"]

# Cosa significa la modalita' scelta dall'utente, detto all'agente. Il runtime la
# fa comunque rispettare (capability filtrate nel router, scritture rifiutate in
# `agents/chat_mode.py`): questo testo serve a far spiegare bene il limite,
# non a imporlo.
CHAT_MODE_CONTRACTS: dict[str, str] = {
    "plan": (
        "Modalita' Piano: l'utente vuole capire e decidere, non applicare. Puoi "
        "esplorare, raccogliere evidenze, preparare e correggere il piano di "
        "processo. Non puoi modificare il canvas ne' approvare una review: se "
        "servisse, dillo e proponi il passaggio a Modifica o Agente."
    ),
    "edit": (
        "Modalita' Modifica: l'utente ha gia' deciso cosa cambiare. Applica la "
        "modifica richiesta in modo puntuale e verificala. Non rifare il piano e "
        "non ricostruire il modello da zero."
    ),
    "agent": (
        "Modalita' Agente: l'utente ti affida il ciclo completo. Pianifica, "
        "applica e verifica fino a chiudere la richiesta."
    ),
}
VALID_AGENT_SCOPE_TYPES: set[str] = {"consultant", "project", "process", "canvas"}
MAX_CURRENT_BPMN_XML_CHARS = 80_000
MAX_STATE_ARTIFACT_CHARS = 40_000


def agent_scope_type(scope: ChatScope | None) -> AgentScopeType:
    if scope is None:
        return "consultant"
    return scope.type


def agent_scope_state(
    scope: ChatScope | None,
    chat_mode: ChatMode | None = None,
) -> dict[str, str | None]:
    scope_type = agent_scope_type(scope)
    return {
        "scope_type": scope_type,
        "chat_mode": chat_mode or DEFAULT_CHAT_MODE,
        "scope_key": chat_scope_key(scope),
        "project_id": getattr(scope, "project_id", None),
        "process_id": getattr(scope, "process_id", None),
        "bpmn_model_id": getattr(scope, "bpmn_model_id", None),
        "current_bpmn_xml": getattr(scope, "current_bpmn_xml", None),
    }


def build_scope_system_prompt(state: dict) -> str:
    scope_type = str(state.get("scope_type") or "consultant")
    chat_mode = str(state.get("chat_mode") or "agent")
    lines = [
        "Contesto operativo del thread.",
        "Lo scope arriva dalla UI/backend: non dedurlo dal testo utente.",
        f"chat_scope: {scope_type}",
        f"scope_key: {state.get('scope_key') or 'consultant'}",
        "",
        f"chat_mode: {chat_mode}",
        CHAT_MODE_CONTRACTS[chat_mode],
    ]

    if state.get("project_id"):
        lines.append(f"project_id: {state['project_id']}")
    if state.get("process_id"):
        lines.append(f"process_id: {state['process_id']}")
    if state.get("bpmn_model_id"):
        lines.append(f"bpmn_model_id: {state['bpmn_model_id']}")
    if state.get("project_name"):
        lines.append(f"project_name: {state['project_name']}")
    if state.get("client_name"):
        lines.append(f"client_name: {state['client_name']}")
    if state.get("project_phase"):
        lines.append(f"project_phase: {state['project_phase']}")
    if state.get("project_status"):
        lines.append(f"project_status: {state['project_status']}")
    if state.get("progress") is not None:
        lines.append(f"project_progress: {state['progress']}")
    if state.get("next_step"):
        lines.append(f"project_next_step: {state['next_step']}")
    if state.get("process_name"):
        lines.append(f"process_name: {state['process_name']}")

    if scope_type == "project":
        project_snapshot = {
            "processes": state.get("project_processes") or [],
            "sources": state.get("project_sources") or [],
            "decisions": state.get("project_decisions") or [],
            "deliverables": state.get("project_deliverables") or [],
            "open_issues": state.get("project_open_issues") or [],
        }
        lines.extend(
            [
                "",
                "Snapshot progetto corrente precaricato dal workspace DB:",
                _state_value_to_text(project_snapshot, MAX_STATE_ARTIFACT_CHARS),
            ]
        )

    if state.get("readiness_score") is not None:
        lines.append(f"readiness_score: {state['readiness_score']}")
    if state.get("missing_information"):
        lines.append(
            "missing_information: "
            + _state_value_to_text(state["missing_information"], MAX_STATE_ARTIFACT_CHARS)
        )

    open_questions = state.get("review_open_questions") or []
    if open_questions:
        answered = [item for item in open_questions if item.get("answer")]
        unanswered = [item for item in open_questions if not item.get("answer")]
        lines.append("")
        if answered:
            lines.append(
                "Domande del piano gia' decise dal consulente. Sono decisioni sue: "
                "non riproporle e tienine conto quando rivedi il piano."
            )
            for item in answered:
                lines.append(f"- {item.get('question')} -> {item.get('answer')}")
        if unanswered:
            lines.append(
                "Domande del piano ancora aperte. Quando le riproponi, dai da 2 a 4 "
                "alternative concrete fra cui scegliere, non una domanda a campo libero."
            )
            for item in unanswered:
                options = ", ".join(
                    str(option.get("label")) for option in item.get("options") or []
                )
                suffix = f" [alternative gia' proposte: {options}]" if options else ""
                lines.append(f"- ({item.get('severity')}) {item.get('question')}{suffix}")

    if state.get("process_understanding"):
        lines.extend(
            [
                "",
                "ProcessUnderstanding corrente nello state:",
                _state_value_to_text(state["process_understanding"], MAX_STATE_ARTIFACT_CHARS),
            ]
        )
    if state.get("process_understanding_diagnostics"):
        lines.extend(
            [
                "",
                "Diagnostica ProcessUnderstanding corrente:",
                _state_value_to_text(state["process_understanding_diagnostics"], MAX_STATE_ARTIFACT_CHARS),
            ]
        )
    if state.get("process_quality_report"):
        lines.extend(
            [
                "",
                "Quality report ProcessUnderstanding corrente:",
                _state_value_to_text(state["process_quality_report"], MAX_STATE_ARTIFACT_CHARS),
            ]
        )

    if state.get("bpmn_semantic_model"):
        lines.extend(
            [
                "",
                "BPMNSemanticModel corrente nello state:",
                _state_value_to_text(state["bpmn_semantic_model"], MAX_STATE_ARTIFACT_CHARS),
            ]
        )

    effective_bpmn_xml = state.get("effective_bpmn_xml")
    if scope_type == "canvas" and effective_bpmn_xml:
        xml = str(effective_bpmn_xml)
        truncated = len(xml) > MAX_CURRENT_BPMN_XML_CHARS
        if truncated:
            xml = xml[:MAX_CURRENT_BPMN_XML_CHARS]
        lines.extend(
            [
                "",
                f"effective_bpmn_xml_source: {state.get('effective_bpmn_xml_source') or 'unknown'}",
                "effective_bpmn_xml:",
                xml,
                f"effective_bpmn_xml_truncated: {str(truncated).lower()}",
            ]
        )

    if scope_type == "canvas" and state.get("canvas_loop_status"):
        loop_snapshot = {
            "status": state.get("canvas_loop_status"),
            "attempt": state.get("canvas_loop_attempt") or 0,
            "max_attempts": state.get("canvas_loop_max_attempts") or 0,
            "objective": state.get("canvas_objective"),
            "next_actions": state.get("canvas_next_actions") or [],
            "latest_validation": state.get("canvas_last_validation") or state.get("validation_report"),
            "task_log": state.get("canvas_task_log") or [],
        }
        lines.extend(
            [
                "",
                "Canvas completion loop corrente.",
                "Se lo status e' needs_fix, correggi solo i problemi indicati dalla latest_validation e poi lascia verificare di nuovo il canvas.",
                _state_value_to_text(loop_snapshot, MAX_STATE_ARTIFACT_CHARS),
            ]
        )

    current_bpmn_xml = state.get("current_bpmn_xml")
    if scope_type == "canvas" and current_bpmn_xml:
        xml = str(current_bpmn_xml)
        truncated = len(xml) > MAX_CURRENT_BPMN_XML_CHARS
        if truncated:
            xml = xml[:MAX_CURRENT_BPMN_XML_CHARS]
        lines.extend(
            [
                "",
                "BPMN XML corrente del canvas, letto dalla UI prima dell'invio del messaggio.",
                "Questo XML e' transiente e puo' includere modifiche non ancora salvate nel backend.",
                "Usalo come sorgente primaria quando l'utente chiede di leggere o interpretare il canvas corrente.",
                f"current_bpmn_xml_truncated: {str(truncated).lower()}",
                "current_bpmn_xml:",
                xml,
            ]
        )

    lines.extend(
        [
            "",
            "Usa gli id disponibili come confini operativi del thread.",
            "Non mischiare dati tra chat generale, progetto, processo e canvas.",
            "Se un'operazione richiede un id mancante, chiedi il contesto invece di inventarlo.",
            "I tool disponibili per questo scope definiscono le azioni consentite.",
        ]
    )
    return "\n".join(lines)


def tool_scope_type(scope_type: str | None) -> AgentScopeType:
    if scope_type in VALID_AGENT_SCOPE_TYPES:
        return scope_type
    return "consultant"


def _state_value_to_text(value, max_chars: int) -> str:
    if isinstance(value, str):
        text = value
    elif isinstance(value, BaseModel):
        text = value.model_dump_json(indent=2)
    else:
        text = json.dumps(value, ensure_ascii=False, indent=2)

    if len(text) <= max_chars:
        return text

    return text[:max_chars] + "\n...[troncato]"
