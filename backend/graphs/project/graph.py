from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
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
from backend.graphs.routing_contracts import (
    ProjectRoutingDecision,
    authorize_routing_decision,
    invalid_project_decision,
    invoke_structured_router,
    parse_routing_decision,
)


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
You are the reasoning layer, not the execution controller.
Propose exactly one route for the latest user request using project state, intent and ownership.

Routes:
- direct: project-level discussion, project context retrieval, project evidence/interview saving or retrieval, project-scoped GraphRAG, light synthesis, scope clarification, source/decision awareness, or general project coordination.
- delivery: phase, progress, milestones, deliverables, risks, blockers, next step, weekly plan, or project status update.
- process_coordination: multiple processes in one project, process sequencing, readiness matrix, cross-process dependencies, interview needs by process, or handoff planning.
- delegate_process: deep work on one process, AS-IS/TO-BE discovery, evidence synthesis for one process, readiness, or BPMN semantic review.
- delegate_canvas: BPMN XML, canvas inspection, canvas edits, validation, layout, versions, or approval.
- clarification: project intent is unclear or required ids/context are missing.

Return structured output matching the ProjectRoutingDecision schema.
Set goal, intent, next_action and suggested_capability separately.
Suggested capability must be registered, for example project.direct,
project.delivery, project.process_coordination, project.process_delegation or
project.canvas_delegation. If process/canvas delegation has an ambiguous target,
route to clarification.
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


def project_routing_state(
    decision: ProjectRoutingDecision,
    *,
    user_request: str = "",
    state: dict | None = None,
    parse_source: str = "structured",
    parse_error: str | None = None,
) -> dict:
    authorization = authorize_routing_decision(
        owner="project",
        decision=decision,
        state=state,
        parse_source=parse_source,
        parse_error=parse_error,
    )
    route = authorization["route"]
    target = authorization["target"]
    reason = decision.reason or decision.reasoning_summary or "Project router decision."
    expected_result = decision.expected_result or ""
    project_mode = decision.project_mode or ("clarification" if route == "clarification" else None)
    project_objective = decision.project_objective or decision.goal or expected_result or None
    needs_clarification = bool(decision.needs_clarification or route == "clarification")
    delegation_payload = {
        "target": target,
        "route": route,
        "user_request": user_request,
        "entity_hints": decision.entity_hints,
        "expected_result": expected_result,
        "reason": reason,
        "goal": decision.goal,
        "intent": decision.intent,
        "next_action": decision.next_action,
        "authorized_capability": authorization["authorized_capability"],
    }
    routing_event = {
        "owner": "project",
        "route": route,
        "proposed_route": authorization["proposed_route"],
        "target": target,
        "confidence": decision.confidence,
        "needs_clarification": needs_clarification,
        "status": authorization["status"],
        "goal": decision.goal,
        "intent": decision.intent,
        "next_action": decision.next_action,
        "proposed_capability": authorization["proposed_capability"],
        "authorized_capability": authorization["authorized_capability"],
        "blocking_conditions": authorization["blocking_conditions"],
        "required_context": decision.required_context,
        "expected_next_state": decision.expected_next_state,
        "termination_reason": authorization["termination_reason"],
        "parse_source": authorization["parse_source"],
        "reason": reason,
        "reasoning_summary": decision.reasoning_summary,
    }

    return {
        "project_route": route,
        "project_mode": project_mode,
        "project_objective": project_objective,
        "delegation_target": target,
        "delegation_reason": reason,
        "routing_confidence": decision.confidence,
        "needs_clarification": needs_clarification,
        "clarification_question": decision.clarification_question,
        "entity_hints": decision.entity_hints,
        "delegation_payload": delegation_payload,
        "routing_trace": [routing_event],
        "delegation_events": [delegation_payload] if target else [],
        "goal": decision.goal,
        "intent": decision.intent,
        "next_action": decision.next_action,
        "suggested_capability": authorization["proposed_capability"],
        "authorized_capability": authorization["authorized_capability"],
        "orchestration_status": authorization["status"],
        "termination_reason": authorization["termination_reason"],
        "blocking_conditions": authorization["blocking_conditions"],
        "required_context": decision.required_context,
        "reasoning_summary": decision.reasoning_summary,
    }


def parse_project_router_json(content: str, user_request: str = "", state: dict | None = None) -> dict:
    decision, parse_source, parse_error = parse_routing_decision(
        content,
        ProjectRoutingDecision,
        invalid_project_decision,
    )
    return project_routing_state(
        decision,
        user_request=user_request,
        state=state,
        parse_source=parse_source,
        parse_error=parse_error,
    )


def build_project_router(llm):
    def route_project_intent(state: ProjectState, config: RunnableConfig) -> dict:
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
            decision, parse_source, parse_error = invoke_structured_router(
                llm,
                ProjectRoutingDecision,
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
                ],
                config=config,
                invalid_factory=invalid_project_decision,
            )
        except Exception:
            decision = invalid_project_decision("Structured router failed unexpectedly.")
            parse_source = "invalid"
            parse_error = "Structured router failed unexpectedly."

        return project_routing_state(
            decision,
            user_request=user_text,
            state=state,
            parse_source=parse_source,
            parse_error=parse_error,
        )

    return route_project_intent


def selected_project_route(state: ProjectState) -> str:
    return state.get("project_route") or "direct"


def ask_project_clarification(state: ProjectState) -> dict:
    return {
        "messages": [
            AIMessage(
                content=state.get("clarification_question")
                or "Mi serve un chiarimento sul progetto o sul processo target prima di procedere."
            )
        ]
    }


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
    workflow.add_node("ask_project_clarification", ask_project_clarification)

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
            "clarification": "ask_project_clarification",
        },
    )
    workflow.add_edge("project_macro_agent", END)
    workflow.add_edge("delivery_subgraph", END)
    workflow.add_edge("process_coordination_subgraph", END)
    workflow.add_edge("delegate_to_process_macro", END)
    workflow.add_edge("delegate_to_canvas_macro", END)
    workflow.add_edge("ask_project_clarification", END)

    return workflow.compile()
