from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import START, END, StateGraph
from pydantic import BaseModel

from backend.graphs.common import build_tool_chat_subgraph
from backend.graphs.consulting.skill_context import load_markdown_skills, tool_prompt_block
from backend.graphs.process.nodes import load_process_context
from backend.graphs.process.state import ProcessState
from backend.graphs.process.subgraphs.discovery import build_discovery_subgraph, discovery_tools
from backend.graphs.process.subgraphs.evidence import build_evidence_subgraph, evidence_tools
from backend.graphs.process.subgraphs.modeling import build_modeling_subgraph, modeling_tools
from backend.graphs.process.tools import PROCESS_TOOL_POLICY
from backend.graphs.routing_contracts import (
    ProcessRoutingDecision,
    authorize_routing_decision,
    invalid_process_decision,
    invoke_structured_router,
    parse_routing_decision,
)


SKILLS_DIR = Path(__file__).resolve().parent / "skills"

PROCESS_SUBGRAPH_CONTRACT = """
Process Macro Agent contract.

{tool_policy}

The Process Macro Agent is the semantic orchestrator for one process workspace.
It owns the transition from process conversation to evidence-backed
ProcessUnderstanding, then to BPMNSemanticModel, then to a narrow Canvas Macro
handoff.

ProcessUnderstanding is the canonical semantic context for AS-IS/BPMN work.
Do not produce BPMN directly from raw text. Discovery and evidence synthesis
must happen before modeling when the input is incomplete, weak, contradictory
or source-sensitive.

Use the preloaded process record, pending review, ProcessUnderstanding,
BPMNSemanticModel, missing information and saved BPMN XML before asking the
user to repeat context.

Enterprise Knowledge Graph retrieval is available through process KG tools.
Treat it as relation-heavy retrieval context and keep workspace DB records as
the authoritative operational state. LlamaIndex can replace the local KG adapter
without changing the tool contract.

{skill_context}
""".format(
    tool_policy=PROCESS_TOOL_POLICY,
    skill_context=load_markdown_skills(SKILLS_DIR),
).strip()


PROCESS_ROUTER_PROMPT = """
You are the Process graph router for DeliR.
You are the reasoning layer, not the execution controller.
Propose the next best engineering action using user goal and current process state.
Do not equate the user's goal with the next executable action.

Routes:
- direct: process-level discussion, existing context retrieval, light explanation, or scope clarification that Process Macro can answer.
- discovery: process boundaries, trigger, start/end, stakeholders, official vs actual process, missing knowledge, interview planning, or discovery readiness.
- evidence: source saving, source custody, claim extraction, confidence, contradictions, evidence coverage, hypotheses, or open questions.
- modeling: ProcessUnderstanding, AS-IS review, BPMNSemanticModel, modeling readiness, semantic BPMN structure, or review before canvas.
- delegate_canvas: BPMN XML, canvas inspection, canvas edits, layout, validation, versions, approval, or saved XML changes.
- clarification: process intent is unclear or required ids/context are missing.

Return structured output matching the ProcessRoutingDecision schema.
Set goal, intent, next_action and suggested_capability separately.
Suggested capability must be registered: process.direct, process.discovery,
process.evidence, process.modeling, process.canvas_handoff or process.clarification.
Use workflow_scope=local_operation for narrow canvas/XML patch requests, single_step
for one bounded capability, and full_workflow only when the user asks for an
end-to-end engineering outcome.
""".strip()


VALID_PROCESS_ROUTES = {
    "direct",
    "discovery",
    "evidence",
    "modeling",
    "delegate_canvas",
    "clarification",
}


ROUTE_TARGETS = {
    "direct": None,
    "discovery": "discovery_subgraph",
    "evidence": "evidence_subgraph",
    "modeling": "modeling_subgraph",
    "delegate_canvas": "canvas_macro",
    "clarification": None,
}


def latest_user_text(state: dict) -> str:
    for message in reversed(state.get("messages", [])):
        role = getattr(message, "type", None) or getattr(message, "role", "")
        if role in {"human", "user"}:
            return str(getattr(message, "content", "") or "")

    return ""


def _artifact_is_present(value) -> bool:
    if value is None:
        return False
    if isinstance(value, BaseModel):
        return True
    return bool(value)


def _artifact_field(value, field: str):
    if value is None:
        return None
    if isinstance(value, BaseModel):
        return getattr(value, field, None)
    if isinstance(value, dict):
        return value.get(field)
    return None


def _artifact_for_prompt(value):
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return value or {}


def process_state_signature(state: dict) -> str:
    diagnostics = state.get("process_understanding_diagnostics")
    quality_report = state.get("process_quality_report")
    return "|".join(
        [
            str(_artifact_is_present(state.get("process_understanding"))),
            str(_artifact_is_present(state.get("bpmn_semantic_model"))),
            str(state.get("readiness_score")),
            str(len(state.get("missing_information") or [])),
            str(bool(_artifact_field(diagnostics, "blocking"))),
            str(bool(_artifact_field(diagnostics, "warnings"))),
            str(_artifact_field(quality_report, "overall_score")),
            str(bool(state.get("saved_bpmn_xml"))),
            str(len(state.get("contradictions") or [])),
            str(len(state.get("process_claims") or [])),
            str(len(state.get("process_gaps") or [])),
        ]
    )


def process_routing_state(
    decision: ProcessRoutingDecision,
    *,
    user_request: str = "",
    state: dict | None = None,
    parse_source: str = "structured",
    parse_error: str | None = None,
) -> dict:
    authorization = authorize_routing_decision(
        owner="process",
        decision=decision,
        state=state,
        parse_source=parse_source,
        parse_error=parse_error,
    )
    state = state or {}
    route = authorization["route"]
    target = authorization["target"]
    reason = decision.reason or decision.reasoning_summary or "Process router decision."
    expected_result = decision.expected_result or ""
    process_mode = decision.process_mode or ("clarification" if route == "clarification" else route)
    process_objective = decision.process_objective or decision.goal or expected_result or None
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
        "workflow_scope": decision.workflow_scope,
        "authorized_capability": authorization["authorized_capability"],
    }
    routing_event = {
        "owner": "process",
        "route": route,
        "proposed_route": authorization["proposed_route"],
        "target": target,
        "confidence": decision.confidence,
        "needs_clarification": needs_clarification,
        "status": authorization["status"],
        "goal": decision.goal,
        "intent": decision.intent,
        "next_action": decision.next_action,
        "workflow_scope": decision.workflow_scope,
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
        "process_route": route,
        "process_mode": process_mode,
        "process_objective": process_objective,
        "process_phase": process_mode,
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
        "workflow_scope": decision.workflow_scope,
        "engineering_loop_iteration": state.get("engineering_loop_iteration", 0),
        "engineering_loop_max_iterations": decision.max_iterations,
        "process_progress_signature": process_state_signature(state),
        "process_continue_loop": False,
    }


def parse_process_router_json(content: str, user_request: str = "", state: dict | None = None) -> dict:
    decision, parse_source, parse_error = parse_routing_decision(
        content,
        ProcessRoutingDecision,
        invalid_process_decision,
    )
    return process_routing_state(
        decision,
        user_request=user_request,
        state=state,
        parse_source=parse_source,
        parse_error=parse_error,
    )


def build_process_router(llm):
    def route_process_intent(state: ProcessState, config: RunnableConfig) -> dict:
        user_text = latest_user_text(state)
        if not user_text:
            return parse_process_router_json(
                '{"route":"direct","confidence":0,"reason":"No user message available."}'
            )

        try:
            decision, parse_source, parse_error = invoke_structured_router(
                llm,
                ProcessRoutingDecision,
                [
                    SystemMessage(content=PROCESS_ROUTER_PROMPT),
                    HumanMessage(
                        content=(
                            "Active scope: process\n\n"
                            f"project_id: {state.get('project_id')}\n"
                            f"process_id: {state.get('process_id')}\n"
                            f"process_name: {state.get('process_name')}\n"
                            f"readiness_score: {state.get('readiness_score')}\n"
                            f"missing_information: {state.get('missing_information') or []}\n"
                            f"has_process_understanding: {_artifact_is_present(state.get('process_understanding'))}\n"
                            "process_understanding_diagnostics: "
                            f"{_artifact_for_prompt(state.get('process_understanding_diagnostics'))}\n"
                            "process_quality_report: "
                            f"{_artifact_for_prompt(state.get('process_quality_report'))}\n"
                            f"has_bpmn_semantic_model: {_artifact_is_present(state.get('bpmn_semantic_model'))}\n"
                            f"has_saved_bpmn_xml: {bool(state.get('saved_bpmn_xml'))}\n\n"
                            "Latest user request:\n"
                            f"{user_text}"
                        )
                    ),
                ],
                config=config,
                invalid_factory=invalid_process_decision,
            )
        except Exception:
            decision = invalid_process_decision("Structured router failed unexpectedly.")
            parse_source = "invalid"
            parse_error = "Structured router failed unexpectedly."

        return process_routing_state(
            decision,
            user_request=user_text,
            state=state,
            parse_source=parse_source,
            parse_error=parse_error,
        )

    return route_process_intent


def selected_process_route(state: ProcessState) -> str:
    return state.get("process_route") or "direct"


def ask_process_clarification(state: ProcessState) -> dict:
    return {
        "messages": [
            AIMessage(
                content=state.get("clarification_question")
                or "Mi serve un chiarimento sul processo o sull'obiettivo prima di procedere."
            )
        ]
    }


def evaluate_process_iteration(state: ProcessState) -> dict:
    iteration = int(state.get("engineering_loop_iteration") or 0) + 1
    max_iterations = int(state.get("engineering_loop_max_iterations") or 2)
    previous_signature = state.get("process_progress_signature")
    current_signature = process_state_signature(state)
    no_progress_count = int(state.get("process_no_progress_count") or 0)

    if previous_signature == current_signature:
        no_progress_count += 1
    else:
        no_progress_count = 0

    workflow_scope = state.get("workflow_scope") or "single_step"
    continue_loop = (
        workflow_scope == "full_workflow"
        and iteration < max_iterations
        and no_progress_count == 0
        and state.get("process_route") not in {"direct", "clarification", "delegate_canvas"}
    )
    termination_reason = state.get("termination_reason")

    if not continue_loop:
        if iteration >= max_iterations and workflow_scope == "full_workflow":
            termination_reason = "SAFE_LIMIT_REACHED"
        elif no_progress_count > 0 and workflow_scope == "full_workflow":
            termination_reason = "BLOCKED_NO_PROGRESS"
        else:
            termination_reason = termination_reason or "DONE"

    return {
        "engineering_loop_iteration": iteration,
        "process_no_progress_count": no_progress_count,
        "process_progress_signature": current_signature,
        "process_continue_loop": continue_loop,
        "termination_reason": termination_reason,
        "routing_trace": [
            {
                "owner": "process",
                "event": "engineering_loop_evaluation",
                "iteration": iteration,
                "max_iterations": max_iterations,
                "no_progress_count": no_progress_count,
                "continue_loop": continue_loop,
                "termination_reason": termination_reason,
            }
        ],
    }


def selected_process_loop_transition(state: ProcessState) -> str:
    return "continue" if state.get("process_continue_loop") else "end"


def delegate_to_canvas_macro(state: ProcessState) -> dict:
    return {
        "messages": [
            AIMessage(
                content=(
                    "Questo lavoro appartiene al Canvas Macro Agent. "
                    "Prepara un handoff canvas dalla chat processo, poi usa la "
                    "chat canvas per XML BPMN, layout, validazione, versioni o approvazione."
                )
            )
        ]
    }


def build_process_subgraph(tools: list, llm, llm_with_tools, build_context_messages):
    process_macro_agent = build_tool_chat_subgraph(
        state_schema=ProcessState,
        tools=tools,
        llm_with_tools=llm_with_tools,
        build_context_messages=build_context_messages,
        subgraph_contract=PROCESS_SUBGRAPH_CONTRACT + "\n\n" + tool_prompt_block(tools),
        agent_node_name="process_macro_agent",
        tool_node_name="process_macro_tools",
    )

    workflow = StateGraph(ProcessState)
    workflow.add_node("load_process_context", load_process_context)
    workflow.add_node("process_router", build_process_router(llm))
    workflow.add_node("process_macro_agent", process_macro_agent)
    workflow.add_node(
        "discovery_subgraph",
        build_discovery_subgraph(
            llm_with_tools=llm.bind_tools(discovery_tools),
            build_context_messages=build_context_messages,
        ),
    )
    workflow.add_node(
        "evidence_subgraph",
        build_evidence_subgraph(
            llm_with_tools=llm.bind_tools(evidence_tools),
            build_context_messages=build_context_messages,
        ),
    )
    workflow.add_node(
        "modeling_subgraph",
        build_modeling_subgraph(
            llm_with_tools=llm.bind_tools(modeling_tools),
            build_context_messages=build_context_messages,
        ),
    )
    workflow.add_node("delegate_to_canvas_macro", delegate_to_canvas_macro)
    workflow.add_node("ask_process_clarification", ask_process_clarification)
    workflow.add_node("evaluate_process_iteration", evaluate_process_iteration)

    workflow.add_edge(START, "load_process_context")
    workflow.add_edge("load_process_context", "process_router")
    workflow.add_conditional_edges(
        "process_router",
        selected_process_route,
        {
            "direct": "process_macro_agent",
            "discovery": "discovery_subgraph",
            "evidence": "evidence_subgraph",
            "modeling": "modeling_subgraph",
            "delegate_canvas": "delegate_to_canvas_macro",
            "clarification": "ask_process_clarification",
        },
    )
    workflow.add_edge("process_macro_agent", END)
    workflow.add_edge("discovery_subgraph", "evaluate_process_iteration")
    workflow.add_edge("evidence_subgraph", "evaluate_process_iteration")
    workflow.add_edge("modeling_subgraph", "evaluate_process_iteration")
    workflow.add_conditional_edges(
        "evaluate_process_iteration",
        selected_process_loop_transition,
        {
            "continue": "load_process_context",
            "end": END,
        },
    )
    workflow.add_edge("delegate_to_canvas_macro", END)
    workflow.add_edge("ask_process_clarification", END)

    return workflow.compile()
