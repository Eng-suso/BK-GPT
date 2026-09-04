import json
import re
from typing import Any, Protocol

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from backend.memory.procedural.skill_loader import (
    MAX_SKILLS_PER_TURN,
    build_skill_context_from_names,
    load_skill_registry,
    normalize_selected_skill_names,
    recent_user_text,
)
from backend.llm_streaming import stream_to_text


CONSULTANT_CONTEXT_CATEGORIES = {
    "general_strategy": (
        "Consultant positioning, target market, offers, business priorities, "
        "professional differentiation, or high-level consulting model."
    ),
    "delivery_method": (
        "How the consultant delivers work: engagement phases, discovery, workshops, "
        "deliverables, validation, stakeholder management, or quality standards."
    ),
    "sales_method": (
        "How the consultant sells: ICP, prospecting, sales calls, objections, pricing, "
        "commercial proposals, demos, follow-up, or qualification."
    ),
    "content_style": (
        "Public or commercial communication style: LinkedIn, email, scripts, landing copy, "
        "tone, message structure, storytelling, or examples."
    ),
    "client_project_context": (
        "Specific client or project context: client name, stakeholders, local process, "
        "client constraints, project notes, local decisions, or project evidence."
    ),
    "process_bpmn": (
        "Specialist process-consulting context: process discovery, As-Is, To-Be, BPMN, "
        "gateways, lanes, pools, handoffs, evidence-backed modeling, validation, or analysis."
    ),
    "personal_preferences": (
        "Sohay's personal preferences for using the assistant or working together: response "
        "format, detail level, language, brainstorming style, when to code versus reason, "
        "or personal operating preferences."
    ),
}

MEMORY_TYPES = {"semantic", "episodic", "procedural", "none"}


class ContextClassifier(Protocol):
    def stream(self, input: Any, config: RunnableConfig | None = None, **kwargs: Any):
        ...


def empty_classification() -> dict:
    return {
        "consultant_context_category": "none",
        "consultant_context_confidence": 0.0,
        "memory_type": "none",
        "should_save_memory": False,
        "suggested_memory_category": None,
        "consultant_context_reason": "No consultant context detected.",
        "active_skill_names": [],
        "skill_selection_reason": "No procedural skill needed.",
        "active_skill_context": "",
    }


def build_classification_prompt(user_text: str) -> list:
    skill_registry = [
        {
            "name": skill.name,
            "description": skill.description,
        }
        for skill in load_skill_registry()
    ]

    return [
        SystemMessage(
            content=(
                "You classify consultant context and select procedural Markdown skills for a LangGraph consultant agent. "
                "Do not answer the user and do not save memory. "
                "Use one category from the provided taxonomy, or 'none' if no consultant context is present. "
                "Do not classify product-engineering direction or software constraints as consultant context unless "
                "they directly describe Sohay's consulting method, communication, sales, delivery, process/BPMN work, "
                "client project context, or personal work preferences. "
                "Select procedural skills only from the provided skill registry. "
                f"Select at most {MAX_SKILLS_PER_TURN} skills. Select no skills for ordinary chat, small talk, "
                "or tasks that do not need a specialized consultant procedure. "
                "Return only valid JSON with this exact shape: "
                '{"consultant_context_category":"category_or_none",'
                '"consultant_context_confidence":0.0,'
                '"memory_type":"semantic|episodic|procedural|none",'
                '"should_save_memory":false,'
                '"suggested_memory_category":null,'
                '"consultant_context_reason":"brief reason",'
                '"active_skill_names":["skill_name"],'
                '"skill_selection_reason":"brief reason"}'
            )
        ),
        HumanMessage(
            content=(
                "Taxonomy:\n"
                f"{json.dumps(CONSULTANT_CONTEXT_CATEGORIES, ensure_ascii=False, indent=2)}\n\n"
                "Memory type guidance:\n"
                "- semantic: stable facts or recurring preferences about the consultant.\n"
                "- episodic: dated source-backed events such as interviews, calls, decisions, notes, feedback.\n"
                "- procedural: reusable ways the consultant works.\n"
                "- none: temporary, trivial, ordinary chat, or not consultant context.\n\n"
                "Procedural skill registry:\n"
                f"{json.dumps(skill_registry, ensure_ascii=False, indent=2)}\n\n"
                "Recent user messages:\n"
                f"{user_text}\n\n"
                "Return JSON only."
            )
        ),
    ]


def normalize_category(value: str) -> str:
    category = str(value or "none").strip().lower()

    if category in CONSULTANT_CONTEXT_CATEGORIES or category == "none":
        return category

    return "none"


def normalize_memory_type(value: str) -> str:
    memory_type = str(value or "none").strip().lower()

    if memory_type in MEMORY_TYPES:
        return memory_type

    return "none"


def parse_confidence(value) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.0

    return max(0.0, min(confidence, 1.0))


def parse_classifier_response(content: str) -> dict:
    text = str(content or "").strip()

    if not text:
        return empty_classification()

    json_match = re.search(r"\{.*\}", text, re.DOTALL)
    if json_match:
        text = json_match.group(0)

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return empty_classification()

    category = normalize_category(payload.get("consultant_context_category"))
    memory_type = normalize_memory_type(payload.get("memory_type"))
    suggested_category = payload.get("suggested_memory_category")
    valid_skill_names = {skill.name for skill in load_skill_registry()}
    active_skill_names = normalize_selected_skill_names(
        payload.get("active_skill_names", []),
        valid_skill_names,
    )

    if category == "none":
        memory_type = "none"
        should_save_memory = False
        suggested_category = None
    else:
        should_save_memory = bool(payload.get("should_save_memory", False))
        if suggested_category is not None:
            suggested_category = str(suggested_category).strip() or None

    return {
        "consultant_context_category": category,
        "consultant_context_confidence": parse_confidence(
            payload.get("consultant_context_confidence")
        ),
        "memory_type": memory_type,
        "should_save_memory": should_save_memory,
        "suggested_memory_category": suggested_category,
        "consultant_context_reason": str(
            payload.get("consultant_context_reason") or ""
        ).strip(),
        "active_skill_names": active_skill_names,
        "skill_selection_reason": str(
            payload.get("skill_selection_reason") or ""
        ).strip(),
        "active_skill_context": build_skill_context_from_names(active_skill_names),
    }


def classify_and_select_context(
    messages: list,
    classifier_llm: ContextClassifier | None,
    config: RunnableConfig | None = None,
) -> dict:
    if classifier_llm is None:
        return empty_classification()

    user_text = recent_user_text(messages)

    if not user_text:
        return empty_classification()

    try:
        response = stream_to_text(
            classifier_llm,
            build_classification_prompt(user_text),
            config=config,
        )
    except Exception:
        return empty_classification()

    return parse_classifier_response(response)


def classify_consultant_context(
    messages: list,
    classifier_llm: ContextClassifier | None,
) -> dict:
    return classify_and_select_context(messages, classifier_llm)


def format_classification_context(state: dict) -> str:
    category = state.get("consultant_context_category")

    if not category or category == "none":
        return ""

    payload = {
        "category": category,
        "confidence": state.get("consultant_context_confidence", 0.0),
        "memory_type": state.get("memory_type", "none"),
        "should_save_memory": state.get("should_save_memory", False),
        "suggested_memory_category": state.get("suggested_memory_category"),
        "reason": state.get("consultant_context_reason", ""),
        "active_skill_names": state.get("active_skill_names", []),
        "skill_selection_reason": state.get("skill_selection_reason", ""),
    }

    return (
        "Consultant context classification for this turn. "
        "Use it to route memory and keep responses aligned with the consultant brain. "
        "Do not mention this classification unless the user asks.\n\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )
