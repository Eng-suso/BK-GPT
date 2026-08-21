import json
import re
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import START, END, StateGraph

from backend.graphs.common import build_tool_chat_subgraph
from backend.graphs.consulting.skill_context import load_markdown_skills, tool_prompt_block
from backend.graphs.process.nodes import load_process_context
from backend.graphs.process.state import ProcessState
from backend.graphs.process.subgraphs.discovery import build_discovery_subgraph, discovery_tools
from backend.graphs.process.subgraphs.evidence import build_evidence_subgraph, evidence_tools
from backend.graphs.process.subgraphs.modeling import build_modeling_subgraph, modeling_tools
from backend.graphs.process.tools import PROCESS_TOOL_POLICY


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
Choose exactly one route for the latest user request using intent and ownership, not keyword matching.

Routes:
- direct: process-level discussion, existing context retrieval, light explanation, or scope clarification that Process Macro can answer.
- discovery: process boundaries, trigger, start/end, stakeholders, official vs actual process, missing knowledge, interview planning, or discovery readiness.
- evidence: source saving, source custody, claim extraction, confidence, contradictions, evidence coverage, hypotheses, or open questions.
- modeling: ProcessUnderstanding, AS-IS review, BPMNSemanticModel, modeling readiness, semantic BPMN structure, or review before canvas.
- delegate_canvas: BPMN XML, canvas inspection, canvas edits, layout, validation, versions, approval, or saved XML changes.
- clarification: process intent is unclear or required ids/context are missing.

Return only JSON:
{
  "route":"direct|discovery|evidence|modeling|delegate_canvas|clarification",
  "confidence":0.0,
  "needs_clarification":false,
  "clarification_question":null,
  "entity_hints":{"project":null,"process":null,"canvas":null,"source":null},
  "process_mode":"discussion|discovery|evidence|modeling|delegation|clarification",
  "process_objective":"brief current objective",
  "expected_result":"brief expected outcome",
  "reason":"brief reason"
}
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


def parse_process_router_json(content: str, user_request: str = "") -> dict:
    text = str(content or "").strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group(0)

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = {}

    route = str(payload.get("route") or "direct").strip()
    if route not in VALID_PROCESS_ROUTES:
        route = "direct"

    try:
        confidence = float(payload.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0

    confidence = max(0.0, min(confidence, 1.0))
    entity_hints = payload.get("entity_hints")
    if not isinstance(entity_hints, dict):
        entity_hints = {}

    reason = str(payload.get("reason") or "Process router decision.").strip()
    needs_clarification = bool(payload.get("needs_clarification", route == "clarification"))
    clarification_question = payload.get("clarification_question")
    if clarification_question is not None:
        clarification_question = str(clarification_question).strip() or None

    expected_result = str(payload.get("expected_result") or "").strip()
    process_mode = str(payload.get("process_mode") or "").strip() or None
    process_objective = str(payload.get("process_objective") or expected_result).strip() or None
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
        "process_route": route,
        "process_mode": process_mode,
        "process_objective": process_objective,
        "process_phase": process_mode,
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


def build_process_router(llm):
    def route_process_intent(state: ProcessState, config: RunnableConfig) -> dict:
        user_text = latest_user_text(state)
        if not user_text:
            return parse_process_router_json(
                '{"route":"direct","confidence":0,"reason":"No user message available."}'
            )

        try:
            response = llm.invoke(
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
                            f"has_process_understanding: {bool(state.get('process_understanding_json'))}\n"
                            f"has_bpmn_semantic_model: {bool(state.get('bpmn_semantic_model_json'))}\n"
                            f"has_saved_bpmn_xml: {bool(state.get('saved_bpmn_xml'))}\n\n"
                            "Latest user request:\n"
                            f"{user_text}"
                        )
                    ),
                ],
                config=config,
            )
        except Exception:
            return parse_process_router_json(
                '{"route":"direct","confidence":0,"reason":"Router unavailable; defaulted to Process Macro Agent."}',
                user_request=user_text,
            )

        return parse_process_router_json(getattr(response, "content", response), user_request=user_text)

    return route_process_intent


def selected_process_route(state: ProcessState) -> str:
    route = state.get("process_route") or "direct"
    if route == "clarification":
        return "direct"
    return route


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
        },
    )
    workflow.add_edge("process_macro_agent", END)
    workflow.add_edge("discovery_subgraph", END)
    workflow.add_edge("evidence_subgraph", END)
    workflow.add_edge("modeling_subgraph", END)
    workflow.add_edge("delegate_to_canvas_macro", END)

    return workflow.compile()
