from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import START, END, StateGraph

from backend.graphs.common import (
    build_tool_chat_subgraph,
    latest_user_text,
    recent_conversation_digest,
)
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
    capability_menu,
    invalid_project_decision,
    parse_routing_decision,
    resolve_routing_decision,
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


PROJECT_ROUTER_PROMPT_TEMPLATE = """
You are the Project graph router for DeliR.
You are the reasoning layer, not the execution controller.
Propose exactly one route for the latest user request using project state, intent and ownership.

Capabilities you may propose:
{capability_menu}

Resolve references before you route. "il processo", "quello", "aggiungilo",
"approvalo", "il secondo" point at an entity already named in the recent
conversation - often by you, in the previous turn. Read the conversation,
resolve the referent and put it in entity_hints. Route to clarification only
when the referent is still ambiguous after reading the conversation, never
because the latest message on its own is short.

The project owns the process records inside it. Registering, creating or adding
a process to this project is project workspace setup, so route it direct: the
Project Macro Agent has the tool. Delegation to Process Macro is for work on a
process that already exists, and never a way to get one created.

When process_count is 0 the project has no processes at all. Process readiness,
cross-process dependencies and process knowledge gaps are not evaluable, and
nothing about a process that does not exist may be inferred. Route direct and
stay on portfolio and scope setup.

Return structured output matching the ProjectRoutingDecision schema.
Set goal, intent, next_action and suggested_capability separately.
""".strip()


def project_router_prompt(chat_mode: str | None = None) -> str:
    """Build the project router prompt for the specified chat mode.
    
    Args:
        chat_mode: Untrusted chat-mode value used to determine the available project
            capabilities. If omitted, the default capability menu is used.
    
    Returns:
        The router prompt containing the capability menu for the selected chat mode.
    """
    return PROJECT_ROUTER_PROMPT_TEMPLATE.format(capability_menu=capability_menu("project", chat_mode))




def project_routing_state(
    decision: ProjectRoutingDecision,
    *,
    user_request: str = "",
    state: dict | None = None,
    parse_source: str = "structured",
    parse_error: str | None = None,
) -> dict:
    """Authorize a project routing decision and convert it into normalized project state.
    
    The resulting state preserves the proposed and authorized routing metadata, records
    the authorization outcome in a routing trace, and includes delegation details when
    a target is authorized. The route and clarification flag remain consistent with the
    authorized decision.
    
    Args:
        decision: The proposed project routing decision.
        user_request: Untrusted user request associated with the decision.
        state: Existing graph state used during authorization.
        parse_source: Source classification for the parsed routing decision.
        parse_error: Parsing error detail, if the decision was produced after a
            parsing failure.
    
    Returns:
        A project state update containing the authorized route, routing metadata,
        delegation payload, clarification details, and authorization status.
    
    Raises:
        Authorization-related errors raised while validating the routing decision.
    
    Side Effects:
        Does not perform persistence or external side effects.
    """
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
    """
    Parse router output and normalize it into project routing state.
    
    Args:
        content (str): Untrusted structured router output to parse.
        user_request (str): Untrusted user request associated with the routing decision.
        state (dict | None): Existing project state to incorporate into the normalized result.
    
    Returns:
        dict: Normalized project routing state containing the parsed decision, parsing metadata,
            and routing information.
    """
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


def _registered_process_names(state: dict) -> str:
    """Formats the names of processes registered in the project state for routing context.
    
    Args:
        state (dict): Untrusted project state containing the optional
            ``project_processes`` collection.
    
    Returns:
        str: A comma-separated list of registered process names, or ``"nessuno"``
            when no named processes are registered.
    """
    names = [
        str(process.get("name") or "")
        for process in state.get("project_processes") or []
        if isinstance(process, dict) and process.get("name")
    ]
    return ", ".join(names) if names else "nessuno"


def build_project_router(llm):
    """
    Create a project-intent routing callable backed by the configured language model.
    
    The callable converts each project request into normalized routing-state updates. It
    uses a direct route when no user message is available and an invalid decision when
    structured routing fails unexpectedly. Routing is performed in memory and does not
    persist state.
    
    Args:
        llm: Language model used to classify project requests.
    
    Returns:
        A callable that accepts project state and runtime configuration and returns
        normalized routing-state updates.
    """
    def route_project_intent(state: ProjectState, config: RunnableConfig) -> dict:
        """
        Route the latest project request to the appropriate project workflow.
        
        Args:
            state (ProjectState): Untrusted project and conversation state used to resolve
                and normalize the routing decision.
            config (RunnableConfig): Runtime configuration for the routing operation.
        
        Returns:
            dict: Normalized project routing state with route, confidence, clarification,
                delegation, and routing-trace metadata. When no user request is available,
                returns a direct route with empty routing metadata.
        
        The function does not persist state. Routing failures are converted into an
        invalid decision and recorded in the returned routing metadata; no exceptions
        are propagated.
        """
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
            decision, parse_source, parse_error = resolve_routing_decision(
                owner="project",
                llm=llm,
                model=ProjectRoutingDecision,
                messages=[
                    SystemMessage(content=project_router_prompt(state.get("chat_mode"))),
                    HumanMessage(
                        content=(
                            "Active scope: project\n\n"
                            f"project_id: {state.get('project_id')}\n"
                            f"project_name: {state.get('project_name')}\n"
                            f"process_count: {len(state.get('project_processes') or [])}\n"
                            f"registered_processes: {_registered_process_names(state)}\n\n"
                            "Recent conversation (resolve references against this):\n"
                            f"{recent_conversation_digest(state)}\n\n"
                            "Latest user request:\n"
                            f"{user_text}"
                        )
                    ),
                ],
                config=config,
                invalid_factory=invalid_project_decision,
                state=state,
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
