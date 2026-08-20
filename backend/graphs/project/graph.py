import json
import re
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import START, END, StateGraph

from backend.graphs.common import build_tool_chat_subgraph
from backend.graphs.consulting.skill_context import load_markdown_skills, tool_prompt_block
from backend.graphs.project.nodes import load_project_context
from backend.graphs.project.state import ProjectState
from backend.graphs.project.subgraphs.delivery import build_delivery_subgraph, delivery_tools
from backend.graphs.project.subgraphs.process_coordination import (
    build_process_coordination_subgraph,
    process_coordination_tools,
)
from backend.graphs.project.tools import PROJECT_TOOL_POLICY


SKILLS_DIR = Path(__file__).resolve().parent / "skills"

PROJECT_SUBGRAPH_CONTRACT = """
Project Macro Agent contract.

{tool_policy}

The Project Macro Agent is the enterprise orchestrator for one project workspace.
It owns project-level conversation, current project context, delivery alignment,
source/decision awareness, deliverable framing and coordination across processes.

It answers directly for project-level synthesis and light coordination. It
delegates delivery planning/status work to the Delivery subgraph, multi-process
sequencing/dependencies/interview planning to the Process Coordination subgraph,
deep AS-IS/BPMN semantic work to Process Macro, and BPMN XML/canvas work to
Canvas Macro.

When the user provides real project evidence in Project Chat, such as an
interview transcript, interview notes, workshop notes, call notes, or a dated
project observation, decide whether it should be saved with the project-scoped
episodic tools before using it. Do not save hypothetical examples or temporary
brainstorming as evidence.

Use project-scoped GraphRAG for relation-heavy questions about the current
project: process dependencies, stakeholder coverage, decision impacts, evidence
links, deliverable dependencies and insight-to-source provenance. Do not use
consulting-level graph retrieval as a substitute for project-scoped relations.

For enterprise evidence, especially interviews or source text that may affect
ROI, process sequence, missing data or inconsistent stakeholder stories, first
prepare graph extraction when useful: relationships, gaps, inconsistencies,
assumptions and ROI impacts. Save those graph fields only if the agent judges
the evidence should become project memory.

{skill_context}
""".format(
    tool_policy=PROJECT_TOOL_POLICY,
    skill_context=load_markdown_skills(SKILLS_DIR),
).strip()


PROJECT_ROUTER_PROMPT = """
You are the Project graph router for DeliR.
Choose exactly one route for the latest user request using intent and ownership, not keyword matching.

Routes:
- direct: project-level discussion, project context retrieval, project evidence/interview saving or retrieval, project-scoped GraphRAG, light synthesis, scope clarification, source/decision awareness, or general project coordination.
- delivery: phase, progress, milestones, deliverables, risks, blockers, next step, weekly plan, or project status update.
- process_coordination: multiple processes in one project, process sequencing, readiness matrix, cross-process dependencies, interview needs by process, or handoff planning.
- delegate_process: deep work on one process, AS-IS/TO-BE discovery, evidence synthesis for one process, readiness, or BPMN semantic review.
- delegate_canvas: BPMN XML, canvas inspection, canvas edits, validation, layout, versions, or approval.
- clarification: project intent is unclear or required ids/context are missing.

Return only JSON:
{
  "route":"direct|delivery|process_coordination|delegate_process|delegate_canvas|clarification",
  "confidence":0.0,
  "needs_clarification":false,
  "clarification_question":null,
  "entity_hints":{"project":null,"process":null,"canvas":null,"source":null,"decision":null},
  "project_mode":"discussion|delivery|coordination|delegation|clarification",
  "project_objective":"brief current objective",
  "expected_result":"brief expected outcome",
  "reason":"brief reason"
}
""".strip()


VALID_PROJECT_ROUTES = {
    "direct",
    "delivery",
    "process_coordination",
    "delegate_process",
    "delegate_canvas",
    "clarification",
}


ROUTE_TARGETS = {
    "direct": None,
    "delivery": "delivery_subgraph",
    "process_coordination": "process_coordination_subgraph",
    "delegate_process": "process_macro",
    "delegate_canvas": "canvas_macro",
    "clarification": None,
}


def latest_user_text(state: dict) -> str:
    for message in reversed(state.get("messages", [])):
        role = getattr(message, "type", None) or getattr(message, "role", "")
        if role in {"human", "user"}:
            return str(getattr(message, "content", "") or "")

    return ""


def parse_project_router_json(content: str, user_request: str = "") -> dict:
    text = str(content or "").strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group(0)

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = {}

    route = str(payload.get("route") or "direct").strip()
    if route not in VALID_PROJECT_ROUTES:
        route = "direct"

    try:
        confidence = float(payload.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0

    confidence = max(0.0, min(confidence, 1.0))
    entity_hints = payload.get("entity_hints")
    if not isinstance(entity_hints, dict):
        entity_hints = {}

    reason = str(payload.get("reason") or "Project router decision.").strip()
    needs_clarification = bool(payload.get("needs_clarification", route == "clarification"))
    clarification_question = payload.get("clarification_question")
    if clarification_question is not None:
        clarification_question = str(clarification_question).strip() or None

    expected_result = str(payload.get("expected_result") or "").strip()
    project_mode = str(payload.get("project_mode") or "").strip() or None
    project_objective = str(payload.get("project_objective") or expected_result).strip() or None
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
        "project_route": route,
        "project_mode": project_mode,
        "project_objective": project_objective,
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


def build_project_router(llm):
    def route_project_intent(state: ProjectState) -> dict:
        user_text = latest_user_text(state)
        if not user_text:
            return {
                "project_route": "direct",
                "project_mode": None,
                "project_objective": None,
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
                    SystemMessage(content=PROJECT_ROUTER_PROMPT),
                    HumanMessage(
                        content=(
                            "Active scope: project\n\n"
                            f"project_id: {state.get('project_id')}\n"
                            f"project_name: {state.get('project_name')}\n"
                            f"process_count: {len(state.get('project_processes') or [])}\n\n"
                            "Latest user request:\n"
                            f"{user_text}"
                        )
                    ),
                ]
            )
        except Exception:
            return {
                "project_route": "direct",
                "project_mode": None,
                "project_objective": None,
                "delegation_target": None,
                "delegation_reason": "Router unavailable; defaulted to Project Macro Agent.",
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
                        "reason": "Router unavailable; defaulted to Project Macro Agent.",
                    }
                ],
                "delegation_events": [],
            }

        return parse_project_router_json(getattr(response, "content", response), user_request=user_text)

    return route_project_intent


def selected_project_route(state: ProjectState) -> str:
    route = state.get("project_route") or "direct"
    if route == "clarification":
        return "direct"
    return route


def delegate_to_process_macro(state: ProjectState) -> dict:
    return {
        "messages": [
            AIMessage(
                content=(
                    "Questo lavoro appartiene al Process Macro Agent. "
                    "Apri o usa la chat processo per discovery AS-IS/TO-BE, "
                    "evidence synthesis, readiness o review BPMN semantica."
                )
            )
        ]
    }


def delegate_to_canvas_macro(state: ProjectState) -> dict:
    return {
        "messages": [
            AIMessage(
                content=(
                    "Questo lavoro appartiene al Canvas Macro Agent. "
                    "Usa la chat canvas per leggere o modificare BPMN XML, "
                    "validare, fare layout o gestire versioni."
                )
            )
        ]
    }


def build_project_subgraph(tools: list, llm, llm_with_tools, build_context_messages):
    project_macro_agent = build_tool_chat_subgraph(
        state_schema=ProjectState,
        tools=tools,
        llm_with_tools=llm_with_tools,
        build_context_messages=build_context_messages,
        subgraph_contract=PROJECT_SUBGRAPH_CONTRACT + "\n\n" + tool_prompt_block(tools),
        agent_node_name="project_macro_agent",
        tool_node_name="project_macro_tools",
    )

    workflow = StateGraph(ProjectState)
    workflow.add_node("load_project_context", load_project_context)
    workflow.add_node("project_router", build_project_router(llm))
    workflow.add_node("project_macro_agent", project_macro_agent)
    workflow.add_node(
        "delivery_subgraph",
        build_delivery_subgraph(
            llm_with_tools=llm.bind_tools(delivery_tools),
            build_context_messages=build_context_messages,
        ),
    )
    workflow.add_node(
        "process_coordination_subgraph",
        build_process_coordination_subgraph(
            llm_with_tools=llm.bind_tools(process_coordination_tools),
            build_context_messages=build_context_messages,
        ),
    )
    workflow.add_node("delegate_to_process_macro", delegate_to_process_macro)
    workflow.add_node("delegate_to_canvas_macro", delegate_to_canvas_macro)

    workflow.add_edge(START, "load_project_context")
    workflow.add_edge("load_project_context", "project_router")
    workflow.add_conditional_edges(
        "project_router",
        selected_project_route,
        {
            "direct": "project_macro_agent",
            "delivery": "delivery_subgraph",
            "process_coordination": "process_coordination_subgraph",
            "delegate_process": "delegate_to_process_macro",
            "delegate_canvas": "delegate_to_canvas_macro",
        },
    )
    workflow.add_edge("project_macro_agent", END)
    workflow.add_edge("delivery_subgraph", END)
    workflow.add_edge("process_coordination_subgraph", END)
    workflow.add_edge("delegate_to_process_macro", END)
    workflow.add_edge("delegate_to_canvas_macro", END)

    return workflow.compile()
