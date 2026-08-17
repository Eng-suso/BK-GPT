from __future__ import annotations

import json
from typing import Literal

from backend.schemas.chat import ChatScope, chat_scope_key


AgentScopeType = Literal["consultant", "project", "process", "canvas"]
VALID_AGENT_SCOPE_TYPES: set[str] = {"consultant", "project", "process", "canvas"}
MAX_CURRENT_BPMN_XML_CHARS = 80_000
MAX_STATE_ARTIFACT_CHARS = 40_000


def agent_scope_type(scope: ChatScope | None) -> AgentScopeType:
    if scope is None:
        return "consultant"
    return scope.type


def agent_scope_state(scope: ChatScope | None) -> dict[str, str | None]:
    scope_type = agent_scope_type(scope)
    return {
        "scope_type": scope_type,
        "scope_key": chat_scope_key(scope),
        "project_id": getattr(scope, "project_id", None),
        "process_id": getattr(scope, "process_id", None),
        "bpmn_model_id": getattr(scope, "bpmn_model_id", None),
        "current_bpmn_xml": getattr(scope, "current_bpmn_xml", None),
    }


def build_scope_system_prompt(state: dict) -> str:
    scope_type = str(state.get("scope_type") or "consultant")
    lines = [
        "Contesto operativo del thread.",
        "Lo scope arriva dalla UI/backend: non dedurlo dal testo utente.",
        f"chat_scope: {scope_type}",
        f"scope_key: {state.get('scope_key') or 'consultant'}",
    ]

    if state.get("project_id"):
        lines.append(f"project_id: {state['project_id']}")
    if state.get("process_id"):
        lines.append(f"process_id: {state['process_id']}")
    if state.get("bpmn_model_id"):
        lines.append(f"bpmn_model_id: {state['bpmn_model_id']}")
    if state.get("process_name"):
        lines.append(f"process_name: {state['process_name']}")

    if state.get("readiness_score") is not None:
        lines.append(f"readiness_score: {state['readiness_score']}")
    if state.get("missing_information"):
        lines.append(
            "missing_information: "
            + _state_value_to_text(state["missing_information"], MAX_STATE_ARTIFACT_CHARS)
        )

    if state.get("process_understanding_json"):
        lines.extend(
            [
                "",
                "ProcessUnderstanding corrente nello state:",
                _state_value_to_text(state["process_understanding_json"], MAX_STATE_ARTIFACT_CHARS),
            ]
        )

    if state.get("bpmn_semantic_model_json"):
        lines.extend(
            [
                "",
                "BPMNSemanticModel corrente nello state:",
                _state_value_to_text(state["bpmn_semantic_model_json"], MAX_STATE_ARTIFACT_CHARS),
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
    else:
        text = json.dumps(value, ensure_ascii=False, indent=2)

    if len(text) <= max_chars:
        return text

    return text[:max_chars] + "\n...[troncato]"
