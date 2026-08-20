import json
import re
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import START, END, StateGraph

from backend.graphs.common import build_tool_chat_subgraph
from backend.graphs.consulting.skill_context import load_markdown_skills, tool_prompt_block
from backend.graphs.consulting.subgraphs.clients import build_clients_subgraph, clients_tools
from backend.graphs.consulting.subgraphs.home import build_home_subgraph, home_tools
from backend.graphs.consulting.subgraphs.setup import build_setup_subgraph, setup_tools
from backend.graphs.consulting.tools import CONSULTING_TOOL_POLICY
from backend.graphs.consulting.state import ConsultingState


SKILLS_DIR = Path(__file__).resolve().parent / "skills"

CONSULTING_SUBGRAPH_CONTRACT = """
Consult Macro Agent contract.

{tool_policy}

The Consult Macro Agent is the strategic orchestrator for Consulting Chat.
It answers directly only for consultant-level strategy, memory, planning,
cross-project synthesis and external research. It delegates operational work
to Home, Clients, Setup, Project, Process or Canvas owners.

{skill_context}
""".format(
    tool_policy=CONSULTING_TOOL_POLICY,
    skill_context=load_markdown_skills(SKILLS_DIR),
).strip()


def latest_user_text(state: dict) -> str:
    for message in reversed(state.get("messages", [])):
        role = getattr(message, "type", None) or getattr(message, "role", "")
        if role in {"human", "user"}:
            return str(getattr(message, "content", "") or "")

    return ""


CONSULTING_ROUTER_PROMPT = """
You are the Consulting graph router for DeliR.
Choose exactly one route for the latest user request using intent and ownership, not keyword matching.

Routes:
- direct: consultant-level strategy, memory, planning, positioning, offers, cross-project synthesis, or general advice.
- home: Home dashboard overview, priorities, risks, recent activity, or next actions.
- clients: client-level record work such as listing, creating, checking, or maintaining clients.
- setup: explicit initial workspace setup involving a client plus a project, process stub, source, or decision.
- delegate_project: project execution, project status, sources, decisions, deliverables, phase, progress, or next step.
- delegate_process: AS-IS/TO-BE discovery, process analysis, evidence synthesis, readiness, or BPMN semantic review.
- delegate_canvas: BPMN XML, canvas inspection, canvas edits, validation, layout, versions, or approval.

Return only JSON:
{
  "route":"direct|home|clients|setup|delegate_project|delegate_process|delegate_canvas",
  "confidence":0.0,
  "needs_clarification":false,
  "clarification_question":null,
  "entity_hints":{"client":null,"project":null,"process":null,"canvas":null},
  "consulting_mode":"strategy|triage|memory|setup|delegation|clarification",
  "consulting_objective":"brief current objective",
  "expected_result":"brief expected outcome",
  "reason":"brief reason"
}
""".strip()


VALID_CONSULTING_ROUTES = {
    "direct",
    "home",
    "clients",
    "setup",
    "delegate_project",
    "delegate_process",
    "delegate_canvas",
}


ROUTE_TARGETS = {
    "direct": None,
    "home": "home_subgraph",
    "clients": "clients_subgraph",
    "setup": "setup_subgraph",
    "delegate_project": "project_macro",
    "delegate_process": "process_macro",
    "delegate_canvas": "canvas_macro",
}


def parse_router_json(content: str, user_request: str = "") -> dict:
    text = str(content or "").strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group(0)

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = {}

    route = str(payload.get("route") or "direct").strip()
    if route not in VALID_CONSULTING_ROUTES:
        route = "direct"

    try:
        confidence = float(payload.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0

    confidence = max(0.0, min(confidence, 1.0))
    entity_hints = payload.get("entity_hints")
    if not isinstance(entity_hints, dict):
        entity_hints = {}

    reason = str(payload.get("reason") or "Consulting router decision.").strip()
    needs_clarification = bool(payload.get("needs_clarification", False))
    clarification_question = payload.get("clarification_question")
    if clarification_question is not None:
        clarification_question = str(clarification_question).strip() or None

    expected_result = str(payload.get("expected_result") or "").strip()
    consulting_mode = str(payload.get("consulting_mode") or "").strip() or None
    consulting_objective = str(payload.get("consulting_objective") or expected_result).strip() or None
    target = ROUTE_TARGETS[route]
    delegation_payload = {
        "target": target,
        "route": route,
        "user_request": user_request,
        "entity_hints": entity_hints,
        "expected_result": expected_result,
        "reason": reason,
    }
    routing_event = {
        "route": route,
        "target": target,
        "confidence": confidence,
        "needs_clarification": needs_clarification,
        "reason": reason,
    }
    delegation_events = []

    if target is not None:
        delegation_events.append(delegation_payload)

    return {
        "consulting_route": route,
        "consulting_mode": consulting_mode,
        "consulting_objective": consulting_objective,
        "delegation_target": target,
        "delegation_reason": reason,
        "routing_confidence": confidence,
        "needs_clarification": needs_clarification,
        "clarification_question": clarification_question,
        "entity_hints": entity_hints,
        "delegation_payload": delegation_payload,
        "routing_trace": [routing_event],
        "delegation_events": delegation_events,
    }


def build_consulting_router(llm):
    def route_consulting_intent(state: ConsultingState) -> dict:
        user_text = latest_user_text(state)
        if not user_text:
            return {
                "consulting_route": "direct",
                "consulting_mode": None,
                "consulting_objective": None,
                "delegation_target": None,
                "delegation_reason": "No user message available.",
                "routing_confidence": 0.0,
                "needs_clarification": False,
                "clarification_question": None,
                "entity_hints": {},
                "delegation_payload": {},
                "routing_trace": [],
                "delegation_events": [],
            }

        try:
            response = llm.invoke(
                [
                    SystemMessage(content=CONSULTING_ROUTER_PROMPT),
                    HumanMessage(
                        content=(
                            "Active scope: consultant\n\n"
                            "Latest user request:\n"
                            f"{user_text}"
                        )
                    ),
                ]
            )
        except Exception:
            return {
                "consulting_route": "direct",
                "consulting_mode": None,
                "consulting_objective": None,
                "delegation_target": None,
                "delegation_reason": "Router unavailable; defaulted to Consult Macro Agent.",
                "routing_confidence": 0.0,
                "needs_clarification": False,
                "clarification_question": None,
                "entity_hints": {},
                "delegation_payload": {},
                "routing_trace": [
                    {
                        "route": "direct",
                        "target": None,
                        "confidence": 0.0,
                        "needs_clarification": False,
                        "reason": "Router unavailable; defaulted to Consult Macro Agent.",
                    }
                ],
                "delegation_events": [],
            }

        return parse_router_json(getattr(response, "content", response), user_request=user_text)

    return route_consulting_intent


def selected_consulting_route(state: ConsultingState) -> str:
    return state.get("consulting_route") or "direct"


def delegate_to_project_macro(state: ConsultingState) -> dict:
    return {
        "messages": [
            AIMessage(
                content=(
                    "Questo lavoro appartiene al Project Macro Agent. "
                    "Apri o usa la chat progetto per gestire fase, fonti, decisioni, "
                    "next step e deliverable del progetto."
                )
            )
        ]
    }


def delegate_to_process_macro(state: ConsultingState) -> dict:
    return {
        "messages": [
            AIMessage(
                content=(
                    "Questo lavoro appartiene al Process Macro Agent. "
                    "Usa la chat processo per discovery AS-IS/TO-BE, evidence, "
                    "readiness e preparazione del modello semantico BPMN."
                )
            )
        ]
    }


def delegate_to_canvas_macro(state: ConsultingState) -> dict:
    return {
        "messages": [
            AIMessage(
                content=(
                    "Questo lavoro appartiene al Canvas Macro Agent. "
                    "Usa la chat canvas per leggere o modificare BPMN XML, validare, "
                    "fare layout o gestire versioni."
                )
            )
        ]
    }


def build_consulting_subgraph(tools: list, llm, llm_with_tools, build_context_messages):
    consult_macro_agent = build_tool_chat_subgraph(
        state_schema=ConsultingState,
        tools=tools,
        llm_with_tools=llm_with_tools,
        build_context_messages=build_context_messages,
        subgraph_contract=(
            CONSULTING_SUBGRAPH_CONTRACT + "\n\n" + tool_prompt_block(tools)
        ),
    )

    workflow = StateGraph(ConsultingState)
    workflow.add_node("consult_router", build_consulting_router(llm))
    workflow.add_node("consult_macro_agent", consult_macro_agent)
    workflow.add_node(
        "home_subgraph",
        build_home_subgraph(
            llm_with_tools=llm.bind_tools(home_tools),
            build_context_messages=build_context_messages,
        ),
    )
    workflow.add_node(
        "clients_subgraph",
        build_clients_subgraph(
            llm_with_tools=llm.bind_tools(clients_tools),
            build_context_messages=build_context_messages,
        ),
    )
    workflow.add_node(
        "setup_subgraph",
        build_setup_subgraph(
            llm_with_tools=llm.bind_tools(setup_tools),
            build_context_messages=build_context_messages,
        ),
    )
    workflow.add_node("delegate_to_project_macro", delegate_to_project_macro)
    workflow.add_node("delegate_to_process_macro", delegate_to_process_macro)
    workflow.add_node("delegate_to_canvas_macro", delegate_to_canvas_macro)

    workflow.add_edge(START, "consult_router")
    workflow.add_conditional_edges(
        "consult_router",
        selected_consulting_route,
        {
            "direct": "consult_macro_agent",
            "home": "home_subgraph",
            "clients": "clients_subgraph",
            "setup": "setup_subgraph",
            "delegate_project": "delegate_to_project_macro",
            "delegate_process": "delegate_to_process_macro",
            "delegate_canvas": "delegate_to_canvas_macro",
        },
    )
    workflow.add_edge("consult_macro_agent", END)
    workflow.add_edge("home_subgraph", END)
    workflow.add_edge("clients_subgraph", END)
    workflow.add_edge("setup_subgraph", END)
    workflow.add_edge("delegate_to_project_macro", END)
    workflow.add_edge("delegate_to_process_macro", END)
    workflow.add_edge("delegate_to_canvas_macro", END)

    return workflow.compile()
