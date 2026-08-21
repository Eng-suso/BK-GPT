import json
import re
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import START, END, StateGraph

from backend.graphs.canvas_edit.models import CanvasRouteDecision
from backend.graphs.canvas_edit.nodes import load_canvas_context
from backend.graphs.canvas_edit.state import CanvasState
from backend.graphs.canvas_edit.subgraphs.construction import build_construction_subgraph, construction_tools
from backend.graphs.canvas_edit.subgraphs.patch_edit import build_patch_edit_subgraph, patch_edit_tools
from backend.graphs.canvas_edit.subgraphs.validation import build_validation_subgraph, validation_tools
from backend.graphs.canvas_edit.tools import CANVAS_TOOL_POLICY, canvas_macro_tools
from backend.graphs.common import build_tool_chat_subgraph
from backend.graphs.consulting.skill_context import load_markdown_skills, tool_prompt_block


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

{skill_context}

{tool_prompts}
""".format(
    tool_policy=CANVAS_TOOL_POLICY,
    skill_context=load_markdown_skills(SKILLS_DIR),
    tool_prompts=tool_prompt_block(canvas_macro_tools),
).strip()


CANVAS_ROUTER_PROMPT = """
You are the Canvas graph router for DeliR.
Choose exactly one route for the latest user request using intent and ownership, not keyword matching.

Routes:
- direct: read-only canvas explanation, scope/context check, or very light discussion.
- patch_edit: local deterministic canvas edits: label/documentation/owner/lane, add/remove one element, connect/reconnect a few elements, layout.
- construction: generate, build, rebuild, redesign, or substantially revise a canvas section from ProcessUnderstanding/BPMNSemanticModel/evidence.
- validation: validate XML, semantic coverage, traceability, layout quality, gateway/lane/path correctness.
- clarification: required ids/context or requested change scope is unclear.

Return only JSON:
{
  "route":"direct|patch_edit|construction|validation|clarification",
  "confidence":0.0,
  "needs_clarification":false,
  "clarification_question":null,
  "entity_hints":{"project":null,"process":null,"canvas":null,"element":null},
  "canvas_mode":"inspection|patch_edit|construction|validation|clarification",
  "canvas_objective":"brief current objective",
  "expected_result":"brief expected outcome",
  "reason":"brief reason"
}
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


def parse_canvas_router_json(content: str, user_request: str = "") -> dict:
    text = str(content or "").strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group(0)

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = {}

    route = str(payload.get("route") or "direct").strip()
    if route not in VALID_CANVAS_ROUTES:
        route = "direct"

    try:
        confidence = float(payload.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(confidence, 1.0))

    entity_hints = payload.get("entity_hints")
    if not isinstance(entity_hints, dict):
        entity_hints = {}

    decision = CanvasRouteDecision(
        route=route,
        confidence=confidence,
        needs_clarification=bool(payload.get("needs_clarification", route == "clarification")),
        clarification_question=payload.get("clarification_question"),
        entity_hints=entity_hints,
        canvas_mode=payload.get("canvas_mode") or "inspection",
        canvas_objective=str(payload.get("canvas_objective") or payload.get("expected_result") or "").strip(),
        expected_result=str(payload.get("expected_result") or "").strip(),
        reason=str(payload.get("reason") or "Canvas router decision.").strip(),
    )
    target = ROUTE_TARGETS[decision.route]
    delegation_payload = {
        "target": target,
        "route": decision.route,
        "user_request": user_request,
        "entity_hints": decision.entity_hints,
        "expected_result": decision.expected_result,
        "reason": decision.reason,
    }
    routing_event = {
        "route": decision.route,
        "target": target,
        "confidence": decision.confidence,
        "needs_clarification": decision.needs_clarification,
        "reason": decision.reason,
    }

    return {
        "canvas_route": decision.route,
        "canvas_mode": decision.canvas_mode,
        "canvas_objective": decision.canvas_objective,
        "delegation_target": target,
        "delegation_reason": decision.reason,
        "routing_confidence": decision.confidence,
        "needs_clarification": decision.needs_clarification,
        "clarification_question": decision.clarification_question,
        "entity_hints": decision.entity_hints,
        "delegation_payload": delegation_payload,
        "routing_trace": [routing_event],
        "delegation_events": [delegation_payload] if target else [],
    }


def build_canvas_router(llm):
    def route_canvas_intent(state: CanvasState, config: RunnableConfig) -> dict:
        user_text = latest_user_text(state)
        if not user_text:
            return parse_canvas_router_json(
                '{"route":"direct","confidence":0,"reason":"No user message available."}'
            )

        try:
            response = llm.invoke(
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
            )
        except Exception:
            return parse_canvas_router_json(
                '{"route":"direct","confidence":0,"reason":"Router unavailable; defaulted to Canvas Macro Agent."}',
                user_request=user_text,
            )

        return parse_canvas_router_json(getattr(response, "content", response), user_request=user_text)

    return route_canvas_intent


def selected_canvas_route(state: CanvasState) -> str:
    route = state.get("canvas_route") or "direct"
    if route == "clarification":
        return "direct"
    return route


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
        },
    )
    workflow.add_edge("canvas_macro_agent", END)
    workflow.add_edge("patch_edit_subgraph", END)
    workflow.add_edge("construction_subgraph", END)
    workflow.add_edge("validation_subgraph", END)

    return workflow.compile()
