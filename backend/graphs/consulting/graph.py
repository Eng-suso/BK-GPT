from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import START, END, StateGraph

from backend.graphs.common import build_tool_chat_subgraph
from backend.graphs.consulting.skill_context import load_markdown_skills, tool_prompt_block
from backend.graphs.consulting.subgraphs.clients import build_clients_subgraph, clients_tools
from backend.graphs.consulting.subgraphs.home import build_home_subgraph, home_tools
from backend.graphs.consulting.subgraphs.setup import build_setup_subgraph, setup_tools
from backend.graphs.consulting.tools import CONSULTING_TOOL_POLICY
from backend.graphs.consulting.state import ConsultingState
from backend.graphs.routing_contracts import (
    ConsultingRoutingDecision,
    authorize_routing_decision,
    invalid_consulting_decision,
    invoke_structured_router,
    parse_routing_decision,
)


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
You are the reasoning layer, not the execution controller.
Propose exactly one route for the latest user request using intent, context and ownership.

Routes:
- direct: consultant-level strategy, memory, planning, positioning, offers, cross-project synthesis, or general advice.
- home: Home dashboard overview, priorities, risks, recent activity, or next actions.
- clients: client-level record work such as listing, creating, checking, or maintaining clients.
- setup: explicit initial workspace setup involving a client plus a project, process stub, source, or decision.
- delegate_project: project execution, project status, sources, decisions, deliverables, phase, progress, or next step.
- delegate_process: AS-IS/TO-BE discovery, process analysis, evidence synthesis, readiness, or BPMN semantic review.
- delegate_canvas: BPMN XML, canvas inspection, canvas edits, validation, layout, versions, or approval.
- clarification: context, owner or entity reference is ambiguous.

Return structured output matching the ConsultingRoutingDecision schema.
Set goal, intent, next_action and suggested_capability separately.
Suggested capability must be one registered capability such as consultant.home,
consultant.clients, consultant.setup, consultant.project_delegation,
consultant.process_delegation, consultant.canvas_delegation or consultant.direct.
If clarification is required, route must be clarification and no delegation should be proposed.
""".strip()


VALID_CONSULTING_ROUTES = {
    "direct",
    "home",
    "clients",
    "setup",
    "delegate_project",
    "delegate_process",
    "delegate_canvas",
    "clarification",
}


ROUTE_TARGETS = {
    "direct": None,
    "home": "home_subgraph",
    "clients": "clients_subgraph",
    "setup": "setup_subgraph",
    "delegate_project": "project_macro",
    "delegate_process": "process_macro",
    "delegate_canvas": "canvas_macro",
    "clarification": None,
}


def consulting_routing_state(
    decision: ConsultingRoutingDecision,
    *,
    user_request: str = "",
    state: dict | None = None,
    parse_source: str = "structured",
    parse_error: str | None = None,
) -> dict:
    authorization = authorize_routing_decision(
        owner="consultant",
        decision=decision,
        state=state,
        parse_source=parse_source,
        parse_error=parse_error,
    )
    route = authorization["route"]
    target = authorization["target"]
    reason = decision.reason or decision.reasoning_summary or "Consulting router decision."
    expected_result = decision.expected_result or ""
    consulting_mode = decision.consulting_mode or ("clarification" if route == "clarification" else None)
    consulting_objective = decision.consulting_objective or decision.goal or expected_result or None
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
        "owner": "consultant",
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
        "consulting_route": route,
        "consulting_mode": consulting_mode,
        "consulting_objective": consulting_objective,
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


def parse_router_json(content: str, user_request: str = "", state: dict | None = None) -> dict:
    decision, parse_source, parse_error = parse_routing_decision(
        content,
        ConsultingRoutingDecision,
        invalid_consulting_decision,
    )
    return consulting_routing_state(
        decision,
        user_request=user_request,
        state=state,
        parse_source=parse_source,
        parse_error=parse_error,
    )


def build_consulting_router(llm):
    def route_consulting_intent(state: ConsultingState, config: RunnableConfig) -> dict:
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
            decision, parse_source, parse_error = invoke_structured_router(
                llm,
                ConsultingRoutingDecision,
                [
                    SystemMessage(content=CONSULTING_ROUTER_PROMPT),
                    HumanMessage(
                        content=(
                            "Active scope: consultant\n\n"
                            "Latest user request:\n"
                            f"{user_text}"
                        )
                    ),
                ],
                config=config,
                invalid_factory=invalid_consulting_decision,
            )
        except Exception:
            decision = invalid_consulting_decision("Structured router failed unexpectedly.")
            parse_source = "invalid"
            parse_error = "Structured router failed unexpectedly."

        return consulting_routing_state(
            decision,
            user_request=user_text,
            state=state,
            parse_source=parse_source,
            parse_error=parse_error,
        )

    return route_consulting_intent


def selected_consulting_route(state: ConsultingState) -> str:
    return state.get("consulting_route") or "direct"


def ask_consulting_clarification(state: ConsultingState) -> dict:
    return {
        "messages": [
            AIMessage(
                content=state.get("clarification_question")
                or "Mi serve un chiarimento prima di instradare correttamente questa richiesta."
            )
        ]
    }


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
    workflow.add_node("ask_consulting_clarification", ask_consulting_clarification)

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
            "clarification": "ask_consulting_clarification",
        },
    )
    workflow.add_edge("consult_macro_agent", END)
    workflow.add_edge("home_subgraph", END)
    workflow.add_edge("clients_subgraph", END)
    workflow.add_edge("setup_subgraph", END)
    workflow.add_edge("delegate_to_project_macro", END)
    workflow.add_edge("delegate_to_process_macro", END)
    workflow.add_edge("delegate_to_canvas_macro", END)
    workflow.add_edge("ask_consulting_clarification", END)

    return workflow.compile()
