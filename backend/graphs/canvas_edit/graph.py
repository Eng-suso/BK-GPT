from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import START, END, StateGraph

from backend.graphs.canvas_edit.nodes import load_canvas_context
from backend.graphs.canvas_edit.state import CanvasState
from backend.graphs.canvas_edit.subgraphs.construction import build_construction_subgraph, construction_tools
from backend.graphs.canvas_edit.subgraphs.patch_edit import build_patch_edit_subgraph, patch_edit_tools
from backend.graphs.canvas_edit.subgraphs.validation import build_validation_subgraph, validation_tools
from backend.graphs.canvas_edit.tools import CANVAS_TOOL_POLICY, canvas_macro_tools
from backend.graphs.common import build_tool_chat_subgraph
from backend.graphs.consulting.skill_context import load_markdown_skills, tool_prompt_block
from backend.graphs.routing_contracts import (
    CanvasRoutingDecision,
    authorize_routing_decision,
    invalid_canvas_decision,
    invoke_structured_router,
    parse_routing_decision,
)


SKILLS_DIR = Path(__file__).resolve().parent / "skills"


CANVAS_SUBGRAPH_CONTRACT = """
Canvas Macro Agent contract.

{tool_policy}

ProcessUnderstanding and BPMNSemanticModel are the semantic base models for
generated or structural BPMN canvas changes. The live canvas XML is still the
source of truth for inspection and local patching.

Distinguish local patching from structural construction:
- local patch/edit: small deterministic changes to labels, documentation,
  element creation/removal, owners, lanes, or sequence flow connections.
- construction: build or rebuild a significant section of the canvas from
  ProcessUnderstanding/BPMNSemanticModel, discovery and evidence context.
- validation: inspect XML and semantic coverage without mutating the model.

The macro agent should route work to a subagent whenever the request is not a
small read-only answer. It should not freely replace BPMN XML.

When answering the user, speak like a senior process consultant, not like a
developer. Prefer business words: passaggio, ruolo responsabile, punto di
decisione, documento, punto da verificare, problema da correggere. Do not expose
XML, ids, sourceRef, targetRef, BPMNSemanticModel, ProcessUnderstanding, DI,
node, gateway or sequenceFlow unless the user explicitly asks for technical BPMN
details.

{skill_context}

{tool_prompts}
""".format(
    tool_policy=CANVAS_TOOL_POLICY,
    skill_context=load_markdown_skills(SKILLS_DIR),
    tool_prompts=tool_prompt_block(canvas_macro_tools),
).strip()


CANVAS_ROUTER_PROMPT = """
You are the Canvas graph router for DeliR.
You are the reasoning layer, not the execution controller.
Propose exactly one route for the latest user request using canvas state, process
semantic context, traceability memory needs and ownership.

Routes:
- direct: read-only canvas explanation, scope/context check, or very light discussion.
- patch_edit: local deterministic canvas edits: label/documentation/owner/lane, add/remove one element, connect/reconnect a few elements, layout.
- construction: generate, build, rebuild, redesign, or substantially revise a canvas section from ProcessUnderstanding/BPMNSemanticModel/evidence.
- validation: validate XML, semantic coverage, traceability, layout quality, gateway/lane/path correctness.
- clarification: required ids/context or requested change scope is unclear.

Return structured output matching the CanvasRoutingDecision schema.
Set goal, intent, next_action and suggested_capability separately.
Suggested capability must be registered: canvas.direct, canvas.patch_edit,
canvas.construction, canvas.validation or canvas.clarification.
For small changes, still consider semantic context and traceability memory before
proposing patch_edit; do not treat local as context-free.
""".strip()


VALID_CANVAS_ROUTES = {"direct", "patch_edit", "construction", "validation", "clarification"}

ROUTE_TARGETS = {
    "direct": None,
    "patch_edit": "patch_edit_subgraph",
    "construction": "construction_subgraph",
    "validation": "validation_subgraph",
    "clarification": None,
}


def latest_user_text(state: dict) -> str:
    for message in reversed(state.get("messages", [])):
        role = getattr(message, "type", None) or getattr(message, "role", "")
        if role in {"human", "user"}:
            return str(getattr(message, "content", "") or "")

    return ""


def canvas_routing_state(
    decision: CanvasRoutingDecision,
    *,
    user_request: str = "",
    state: dict | None = None,
    parse_source: str = "structured",
    parse_error: str | None = None,
) -> dict:
    authorization = authorize_routing_decision(
        owner="canvas",
        decision=decision,
        state=state,
        parse_source=parse_source,
        parse_error=parse_error,
    )
    route = authorization["route"]
    target = authorization["target"]
    reason = decision.reason or decision.reasoning_summary or "Canvas router decision."
    expected_result = decision.expected_result or ""
    canvas_mode = decision.canvas_mode or ("clarification" if route == "clarification" else route)
    canvas_objective = decision.canvas_objective or decision.goal or expected_result or None
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
        "owner": "canvas",
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
        "canvas_route": route,
        "canvas_mode": canvas_mode,
        "canvas_objective": canvas_objective,
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
    }


def parse_canvas_router_json(content: str, user_request: str = "", state: dict | None = None) -> dict:
    decision, parse_source, parse_error = parse_routing_decision(
        content,
        CanvasRoutingDecision,
        invalid_canvas_decision,
    )
    return canvas_routing_state(
        decision,
        user_request=user_request,
        state=state,
        parse_source=parse_source,
        parse_error=parse_error,
    )


def build_canvas_router(llm):
    def route_canvas_intent(state: CanvasState, config: RunnableConfig) -> dict:
        user_text = latest_user_text(state)
        if not user_text:
            return parse_canvas_router_json(
                '{"route":"direct","confidence":0,"reason":"No user message available."}'
            )

        try:
            decision, parse_source, parse_error = invoke_structured_router(
                llm,
                CanvasRoutingDecision,
                [
                    SystemMessage(content=CANVAS_ROUTER_PROMPT),
                    HumanMessage(
                        content=(
                            "Active scope: canvas\n\n"
                            f"project_id: {state.get('project_id')}\n"
                            f"process_id: {state.get('process_id')}\n"
                            f"bpmn_model_id: {state.get('bpmn_model_id')}\n"
                            f"process_name: {state.get('process_name')}\n"
                            f"readiness_score: {state.get('readiness_score')}\n"
                            f"missing_information: {state.get('missing_information') or []}\n"
                            f"has_process_understanding: {bool(state.get('process_understanding'))}\n"
                            f"has_bpmn_semantic_model: {bool(state.get('bpmn_semantic_model'))}\n"
                            f"has_effective_bpmn_xml: {bool(state.get('effective_bpmn_xml'))}\n"
                            f"effective_bpmn_xml_source: {state.get('effective_bpmn_xml_source')}\n\n"
                            "Latest user request:\n"
                            f"{user_text}"
                        )
                    ),
                ],
                config=config,
                invalid_factory=invalid_canvas_decision,
            )
        except Exception:
            decision = invalid_canvas_decision("Structured router failed unexpectedly.")
            parse_source = "invalid"
            parse_error = "Structured router failed unexpectedly."

        return canvas_routing_state(
            decision,
            user_request=user_text,
            state=state,
            parse_source=parse_source,
            parse_error=parse_error,
        )

    return route_canvas_intent


def selected_canvas_route(state: CanvasState) -> str:
    return state.get("canvas_route") or "direct"


def ask_canvas_clarification(state: CanvasState) -> dict:
    return {
        "messages": [
            AIMessage(
                content=state.get("clarification_question")
                or "Mi serve un chiarimento sul canvas o sulla modifica richiesta prima di procedere."
            )
        ]
    }


def build_canvas_subgraph(tools: list, llm, llm_with_tools, build_context_messages):
    canvas_macro_agent = build_tool_chat_subgraph(
        state_schema=CanvasState,
        tools=canvas_macro_tools,
        llm_with_tools=llm.bind_tools(canvas_macro_tools),
        build_context_messages=build_context_messages,
        subgraph_contract=CANVAS_SUBGRAPH_CONTRACT,
        agent_node_name="canvas_macro_agent",
        tool_node_name="canvas_macro_tools",
    )

    workflow = StateGraph(CanvasState)
    workflow.add_node("load_canvas_context", load_canvas_context)
    workflow.add_node("canvas_router", build_canvas_router(llm))
    workflow.add_node("canvas_macro_agent", canvas_macro_agent)
    workflow.add_node(
        "patch_edit_subgraph",
        build_patch_edit_subgraph(
            llm_with_tools=llm.bind_tools(patch_edit_tools),
            build_context_messages=build_context_messages,
        ),
    )
    workflow.add_node(
        "construction_subgraph",
        build_construction_subgraph(
            llm_with_tools=llm.bind_tools(construction_tools),
            build_context_messages=build_context_messages,
        ),
    )
    workflow.add_node(
        "validation_subgraph",
        build_validation_subgraph(
            llm_with_tools=llm.bind_tools(validation_tools),
            build_context_messages=build_context_messages,
        ),
    )
    workflow.add_node("ask_canvas_clarification", ask_canvas_clarification)

    workflow.add_edge(START, "load_canvas_context")
    workflow.add_edge("load_canvas_context", "canvas_router")
    workflow.add_conditional_edges(
        "canvas_router",
        selected_canvas_route,
        {
            "direct": "canvas_macro_agent",
            "patch_edit": "patch_edit_subgraph",
            "construction": "construction_subgraph",
            "validation": "validation_subgraph",
            "clarification": "ask_canvas_clarification",
        },
    )
    workflow.add_edge("canvas_macro_agent", END)
    workflow.add_edge("patch_edit_subgraph", END)
    workflow.add_edge("construction_subgraph", END)
    workflow.add_edge("validation_subgraph", END)
    workflow.add_edge("ask_canvas_clarification", END)

    return workflow.compile()
