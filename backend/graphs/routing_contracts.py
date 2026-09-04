from __future__ import annotations

import json
from typing import Any, Literal

from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


Owner = Literal["consultant", "project", "process", "canvas"]
WorkflowScope = Literal["direct", "local_operation", "single_step", "full_workflow", "clarification"]


class RoutingDecisionBase(BaseModel):
    model_config = ConfigDict(extra="ignore")

    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    needs_clarification: bool = False
    clarification_question: str | None = None
    entity_hints: dict[str, Any] = Field(default_factory=dict)
    goal: str | None = None
    intent: str | None = None
    next_action: str | None = None
    suggested_capability: str | None = None
    blocking_conditions: list[str] = Field(default_factory=list)
    required_context: list[str] = Field(default_factory=list)
    expected_next_state: str | None = None
    expected_result: str = ""
    reasoning_summary: str | None = None
    reason: str = ""

    @model_validator(mode="after")
    def normalize_clarification(self):
        if self.clarification_question is not None:
            self.clarification_question = self.clarification_question.strip() or None
        if self.reasoning_summary is not None:
            self.reasoning_summary = self.reasoning_summary.strip() or None
        if self.reason:
            self.reason = self.reason.strip()
        return self


class ConsultingRoutingDecision(RoutingDecisionBase):
    owner: Literal["consultant"] = "consultant"
    route: Literal[
        "direct",
        "home",
        "clients",
        "setup",
        "delegate_project",
        "delegate_process",
        "delegate_canvas",
        "clarification",
    ] = "direct"
    consulting_mode: Literal["strategy", "triage", "memory", "setup", "delegation", "clarification"] | None = None
    consulting_objective: str | None = None

    @model_validator(mode="after")
    def normalize_route_clarification(self):
        if self.route == "clarification":
            self.needs_clarification = True
            self.consulting_mode = "clarification"
        return self


class ProjectRoutingDecision(RoutingDecisionBase):
    owner: Literal["project"] = "project"
    route: Literal["direct", "delivery", "process_coordination", "delegate_process", "delegate_canvas", "clarification"] = (
        "direct"
    )
    project_mode: Literal["discussion", "delivery", "coordination", "delegation", "clarification"] | None = None
    project_objective: str | None = None

    @model_validator(mode="after")
    def normalize_route_clarification(self):
        if self.route == "clarification":
            self.needs_clarification = True
            self.project_mode = "clarification"
        return self


class ProcessRoutingDecision(RoutingDecisionBase):
    owner: Literal["process"] = "process"
    route: Literal["direct", "discovery", "evidence", "modeling", "delegate_canvas", "clarification"] = "direct"
    process_mode: Literal["discussion", "discovery", "evidence", "modeling", "delegation", "clarification"] | None = None
    process_objective: str | None = None
    workflow_scope: WorkflowScope = "single_step"
    max_iterations: int = Field(
        default=6,
        ge=1,
        le=12,
        description=(
            "Hard safety ceiling on engineering-loop passes, not a target to fill or a way "
            "to force early stopping. Size it to how many evidentiary/modeling steps this task "
            "plausibly needs (discovery, evidence, modeling can each take several passes on a "
            "real task). The loop still stops as soon as workflow_scope/route say the work is done."
        ),
    )

    @model_validator(mode="after")
    def normalize_route_clarification(self):
        if self.route == "clarification":
            self.needs_clarification = True
            self.process_mode = "clarification"
            self.workflow_scope = "clarification"
        return self


class CanvasRoutingDecision(RoutingDecisionBase):
    owner: Literal["canvas"] = "canvas"
    route: Literal["direct", "patch_edit", "construction", "layout", "validation", "clarification"] = "direct"
    canvas_mode: Literal["inspection", "patch_edit", "construction", "layout", "validation", "clarification"] | None = None
    canvas_objective: str | None = None
    workflow_scope: WorkflowScope = "single_step"

    @model_validator(mode="after")
    def normalize_route_clarification(self):
        if self.route == "clarification":
            self.needs_clarification = True
            self.canvas_mode = "clarification"
            self.workflow_scope = "clarification"
        return self


class CapabilitySpec(BaseModel):
    id: str
    owner: Owner
    route: str
    target: str | None = None
    prerequisites: list[str] = Field(default_factory=list)
    description: str = ""


CAPABILITY_REGISTRY: dict[str, CapabilitySpec] = {
    "consultant.direct": CapabilitySpec(id="consultant.direct", owner="consultant", route="direct"),
    "consultant.home": CapabilitySpec(id="consultant.home", owner="consultant", route="home", target="home_subgraph"),
    "consultant.clients": CapabilitySpec(id="consultant.clients", owner="consultant", route="clients", target="clients_subgraph"),
    "consultant.setup": CapabilitySpec(id="consultant.setup", owner="consultant", route="setup", target="setup_subgraph"),
    "consultant.project_delegation": CapabilitySpec(
        id="consultant.project_delegation", owner="consultant", route="delegate_project", target="project_macro"
    ),
    "consultant.process_delegation": CapabilitySpec(
        id="consultant.process_delegation", owner="consultant", route="delegate_process", target="process_macro"
    ),
    "consultant.canvas_delegation": CapabilitySpec(
        id="consultant.canvas_delegation", owner="consultant", route="delegate_canvas", target="canvas_macro"
    ),
    "consultant.clarification": CapabilitySpec(id="consultant.clarification", owner="consultant", route="clarification"),
    "project.direct": CapabilitySpec(id="project.direct", owner="project", route="direct"),
    "project.delivery": CapabilitySpec(id="project.delivery", owner="project", route="delivery", target="delivery_subgraph"),
    "project.process_coordination": CapabilitySpec(
        id="project.process_coordination",
        owner="project",
        route="process_coordination",
        target="process_coordination_subgraph",
    ),
    "project.process_delegation": CapabilitySpec(
        id="project.process_delegation",
        owner="project",
        route="delegate_process",
        target="process_macro",
        prerequisites=["unambiguous_process_target"],
    ),
    "project.canvas_delegation": CapabilitySpec(
        id="project.canvas_delegation",
        owner="project",
        route="delegate_canvas",
        target="canvas_macro",
        prerequisites=["unambiguous_process_target"],
    ),
    "project.clarification": CapabilitySpec(id="project.clarification", owner="project", route="clarification"),
    "process.direct": CapabilitySpec(id="process.direct", owner="process", route="direct"),
    "process.discovery": CapabilitySpec(
        id="process.discovery", owner="process", route="discovery", target="discovery_subgraph", prerequisites=["process_id"]
    ),
    "process.evidence": CapabilitySpec(
        id="process.evidence", owner="process", route="evidence", target="evidence_subgraph", prerequisites=["process_id"]
    ),
    "process.modeling": CapabilitySpec(
        id="process.modeling",
        owner="process",
        route="modeling",
        target="modeling_subgraph",
        prerequisites=["process_id", "process_understanding", "no_critical_contradictions"],
    ),
    "process.canvas_handoff": CapabilitySpec(
        id="process.canvas_handoff",
        owner="process",
        route="delegate_canvas",
        target="canvas_macro",
        prerequisites=["process_id", "bpmn_semantic_model", "readiness_for_canvas"],
    ),
    "process.clarification": CapabilitySpec(id="process.clarification", owner="process", route="clarification"),
    "canvas.direct": CapabilitySpec(id="canvas.direct", owner="canvas", route="direct"),
    "canvas.patch_edit": CapabilitySpec(
        id="canvas.patch_edit",
        owner="canvas",
        route="patch_edit",
        target="patch_edit_subgraph",
        prerequisites=["bpmn_model_id", "effective_bpmn_xml"],
        description="Local deterministic BPMN XML/canvas patch with semantic and memory context available.",
    ),
    "canvas.construction": CapabilitySpec(
        id="canvas.construction",
        owner="canvas",
        route="construction",
        target="construction_subgraph",
        prerequisites=["bpmn_model_id"],
        description=(
            "Build or rebuild canvas sections from existing semantic context, "
            "or prepare that semantic context from a raw process description."
        ),
    ),
    "canvas.layout": CapabilitySpec(
        id="canvas.layout",
        owner="canvas",
        route="layout",
        target="layout_subgraph",
        prerequisites=["bpmn_model_id", "effective_bpmn_xml"],
        description="Repair BPMN diagram layout for readability, spacing, labels and viewport-friendly structure.",
    ),
    "canvas.validation": CapabilitySpec(
        id="canvas.validation",
        owner="canvas",
        route="validation",
        target="validation_subgraph",
        prerequisites=["bpmn_model_id", "effective_bpmn_xml"],
        description="Validate the current canvas against BPMN XML, semantic context and traceability memory.",
    ),
    "canvas.clarification": CapabilitySpec(id="canvas.clarification", owner="canvas", route="clarification"),
}


DEFAULT_CAPABILITY_BY_OWNER_ROUTE: dict[tuple[str, str], str] = {
    (spec.owner, spec.route): spec.id for spec in CAPABILITY_REGISTRY.values()
}


def invalid_consulting_decision(reason: str) -> ConsultingRoutingDecision:
    return ConsultingRoutingDecision(
        route="clarification",
        confidence=0.0,
        needs_clarification=True,
        clarification_question="Mi serve un chiarimento prima di instradare questa richiesta.",
        consulting_mode="clarification",
        consulting_objective="Resolve invalid routing decision.",
        goal="CLARIFY_REQUEST",
        intent="clarification",
        next_action="ASK_CLARIFICATION",
        suggested_capability="consultant.clarification",
        blocking_conditions=[reason],
        expected_next_state="WAITING_FOR_USER",
        reasoning_summary=reason,
        reason=reason,
    )


def invalid_project_decision(reason: str) -> ProjectRoutingDecision:
    return ProjectRoutingDecision(
        route="clarification",
        confidence=0.0,
        needs_clarification=True,
        clarification_question="Mi serve un chiarimento sul progetto o sul processo target prima di procedere.",
        project_mode="clarification",
        project_objective="Resolve invalid routing decision.",
        goal="CLARIFY_REQUEST",
        intent="clarification",
        next_action="ASK_CLARIFICATION",
        suggested_capability="project.clarification",
        blocking_conditions=[reason],
        expected_next_state="WAITING_FOR_USER",
        reasoning_summary=reason,
        reason=reason,
    )


def invalid_process_decision(reason: str) -> ProcessRoutingDecision:
    return ProcessRoutingDecision(
        route="clarification",
        confidence=0.0,
        needs_clarification=True,
        clarification_question="Mi serve un chiarimento sul processo o sull'obiettivo prima di procedere.",
        process_mode="clarification",
        process_objective="Resolve invalid routing decision.",
        workflow_scope="clarification",
        goal="CLARIFY_REQUEST",
        intent="clarification",
        next_action="ASK_CLARIFICATION",
        suggested_capability="process.clarification",
        blocking_conditions=[reason],
        expected_next_state="WAITING_FOR_USER",
        reasoning_summary=reason,
        reason=reason,
    )


def invalid_canvas_decision(reason: str) -> CanvasRoutingDecision:
    return CanvasRoutingDecision(
        route="clarification",
        confidence=0.0,
        needs_clarification=True,
        clarification_question="Mi serve un chiarimento sul canvas o sulla modifica richiesta prima di procedere.",
        canvas_mode="clarification",
        canvas_objective="Resolve invalid routing decision.",
        workflow_scope="clarification",
        goal="CLARIFY_REQUEST",
        intent="clarification",
        next_action="ASK_CLARIFICATION",
        suggested_capability="canvas.clarification",
        blocking_conditions=[reason],
        expected_next_state="WAITING_FOR_USER",
        reasoning_summary=reason,
        reason=reason,
    )


def router_failure_direct_decision(
    model: type[RoutingDecisionBase],
    reason: str,
) -> RoutingDecisionBase:
    common = {
        "confidence": 0.0,
        "needs_clarification": False,
        "goal": "ANSWER_DIRECTLY",
        "intent": "router_failure_recovery",
        "next_action": "ANSWER_WITH_AVAILABLE_CONTEXT_AND_TOOLS",
        "blocking_conditions": [reason],
        "reasoning_summary": reason,
        "reason": reason,
    }

    if model is ConsultingRoutingDecision:
        return ConsultingRoutingDecision(
            route="direct",
            suggested_capability="consultant.direct",
            consulting_mode="triage",
            **common,
        )
    if model is ProjectRoutingDecision:
        return ProjectRoutingDecision(
            route="direct",
            suggested_capability="project.direct",
            project_mode="discussion",
            **common,
        )
    if model is ProcessRoutingDecision:
        return ProcessRoutingDecision(
            route="direct",
            suggested_capability="process.direct",
            process_mode="discussion",
            workflow_scope="direct",
            **common,
        )
    if model is CanvasRoutingDecision:
        return CanvasRoutingDecision(
            route="direct",
            suggested_capability="canvas.direct",
            canvas_mode="inspection",
            workflow_scope="direct",
            **common,
        )

    raise ValueError(f"Unsupported routing decision model: {model}")



def parse_routing_decision(
    content: Any,
    model: type[RoutingDecisionBase],
    invalid_factory,
) -> tuple[RoutingDecisionBase, str, str | None]:
    if isinstance(content, model):
        return content, "structured", None

    try:
        if isinstance(content, BaseModel):
            return model.model_validate(content.model_dump()), "structured_model", None
        if isinstance(content, dict):
            return model.model_validate(content), "dict", None
        if isinstance(content, str):
            return model.model_validate_json(content), "json", None
    except ValidationError as exc:
        reason = f"Invalid routing decision: {exc.errors()[0]['msg']}"
        return invalid_factory(reason), "invalid", reason

    reason = "Invalid routing decision: unsupported router response type."
    return invalid_factory(reason), "invalid", reason


def invoke_structured_router(
    llm,
    model: type[RoutingDecisionBase],
    messages: list[BaseMessage],
    config: RunnableConfig,
    invalid_factory,
) -> tuple[RoutingDecisionBase, str, str | None]:
    try:
        structured_llm = llm.with_structured_output(model, method="function_calling")
        response = structured_llm.invoke(messages, config=config)
        if response is None:
            json_response = _invoke_json_mode_router(llm, model, messages, config)
            if json_response is not None:
                return parse_routing_decision(json_response, model, invalid_factory)
            reason = "Structured router returned no tool call and JSON fallback returned no decision."
            return router_failure_direct_decision(model, reason), "router_recovery_direct", reason
        return parse_routing_decision(response, model, invalid_factory)
    except Exception as exc:
        try:
            json_response = _invoke_json_mode_router(llm, model, messages, config)
            if json_response is not None:
                return parse_routing_decision(json_response, model, invalid_factory)
        except Exception:
            pass
        reason = f"Structured router failed: {type(exc).__name__}: {exc}"
        return router_failure_direct_decision(model, reason), "router_recovery_direct", reason


def _invoke_json_mode_router(
    llm,
    model: type[RoutingDecisionBase],
    messages: list[BaseMessage],
    config: RunnableConfig,
):
    route_field = model.model_fields.get("route")
    route_options = ""
    if route_field is not None:
        route_options = str(route_field.annotation)

    instruction = SystemMessage(
        content=(
            "Return only one valid JSON object matching the routing schema. "
            "Do not include markdown or prose. "
            f"The `route` value must satisfy this type: {route_options}. "
            "Set `suggested_capability` to the registered capability matching the owner and route."
        )
    )
    structured_llm = llm.with_structured_output(model, method="json_mode")
    return structured_llm.invoke([instruction, *messages], config=config)


BLOCKING_CONTRADICTION_SEVERITIES = frozenset({"critical", "blocking", "high"})
CLEARING_CONTRADICTION_RESOLUTIONS = frozenset({"resolved", "not_material"})
DEFAULT_MINIMUM_READINESS_SCORE = 7


def _has_critical_contradiction(state: dict[str, Any]) -> bool:
    """Is some contradiction still open at a severity that should stop modeling?

    Contradictions and the conclusions drawn about them are appended to the same
    list, so they are folded by title with the last record winning: a resolution
    clears an earlier contradiction, and re-raising the same title reopens it.
    Whether a contradiction is settled or immaterial is the agent's call, made
    through the contradiction tool; the runtime only reads the conclusion it
    recorded, and treats "never concluded" as still open.
    """
    latest: dict[str, dict[str, Any]] = {}

    for index, record in enumerate(state.get("contradictions") or []):
        if not isinstance(record, dict):
            continue

        # An untitled contradiction cannot be matched to a resolution, so it gets
        # its own key and stays open - it can never be silently cleared.
        key = str(record.get("title") or record.get("id") or "").strip().casefold() or f"__untitled__{index}"
        entry = latest.setdefault(key, {})

        if record.get("resolution"):
            entry["resolution"] = str(record["resolution"]).strip().casefold()
        else:
            entry["severity"] = str(record.get("severity") or record.get("impact") or "").strip().casefold()
            entry.pop("resolution", None)

    return any(
        entry.get("resolution") not in CLEARING_CONTRADICTION_RESOLUTIONS
        and entry.get("severity") in BLOCKING_CONTRADICTION_SEVERITIES
        for entry in latest.values()
    )


def _classified_gaps(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        gap
        for gap in state.get("process_gaps") or []
        if isinstance(gap, dict) and gap.get("severity")
    ]


def _has_blocking_gap(state: dict[str, Any]) -> bool:
    return any(
        str(gap.get("severity") or "").strip().casefold() == "blocking"
        for gap in _classified_gaps(state)
    )


def minimum_readiness_score(state: dict[str, Any]) -> int:
    """The readiness bar to clear before canvas handoff.

    The modeling agent sets this per process through the readiness tool, which is
    projected into state; the fixed default only applies when it has not judged
    one. A process where a first-pass draft is useful and one where the missing
    points are the approval threshold do not deserve the same bar.
    """
    value = state.get("minimum_readiness_score")
    if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 10:
        return value
    return DEFAULT_MINIMUM_READINESS_SCORE


def _state_value_as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return loaded if isinstance(loaded, dict) else {}
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return {}


def _has_canonical_semantic_model(state: dict[str, Any]) -> bool:
    semantic_model = _state_value_as_dict(
        state.get("bpmn_semantic_model")
    )
    return bool(
        semantic_model.get("flowNodes")
        and semantic_model.get("sequenceFlows")
        and semantic_model.get("compilationPlan")
        and semantic_model.get("sourceProcessUnderstanding")
    )


def missing_prerequisites(spec: CapabilitySpec, state: dict[str, Any]) -> list[str]:
    missing = []
    for prerequisite in spec.prerequisites:
        if prerequisite == "process_id" and not (state.get("process_id") or (state.get("entity_hints") or {}).get("process")):
            missing.append(prerequisite)
        elif prerequisite == "process_understanding" and not _has_canonical_semantic_model(state):
            missing.append(prerequisite)
        elif prerequisite == "bpmn_semantic_model" and not _has_canonical_semantic_model(state):
            if state.get("workflow_scope") == "local_operation" and state.get("saved_bpmn_xml"):
                continue
            missing.append(prerequisite)
        elif prerequisite == "readiness_for_canvas":
            if state.get("workflow_scope") == "local_operation" and state.get("saved_bpmn_xml"):
                continue
            readiness = state.get("readiness_score")
            if readiness is None or readiness < minimum_readiness_score(state):
                missing.append(prerequisite)
            elif _classified_gaps(state):
                # The agent has classified what is still open; a gap it called
                # non-blocking or an optional extension does not hold the canvas.
                if _has_blocking_gap(state):
                    missing.append(prerequisite)
            elif state.get("missing_information"):
                # Nothing classified yet: fall back to treating any open item as
                # blocking rather than guessing on the agent's behalf.
                missing.append(prerequisite)
        elif prerequisite == "no_critical_contradictions" and _has_critical_contradiction(state):
            missing.append(prerequisite)
        elif prerequisite == "unambiguous_process_target":
            hints = state.get("entity_hints") or {}
            processes = state.get("project_processes") or []
            if not hints.get("process") and len(processes) != 1:
                missing.append(prerequisite)
        elif prerequisite == "bpmn_model_id" and not (state.get("bpmn_model_id") or (state.get("entity_hints") or {}).get("canvas")):
            missing.append(prerequisite)
        elif prerequisite == "effective_bpmn_xml" and not (
            state.get("effective_bpmn_xml") or state.get("current_bpmn_xml") or state.get("saved_bpmn_xml")
        ):
            missing.append(prerequisite)
        elif prerequisite == "canvas_semantic_context" and not _has_canonical_semantic_model(state):
            missing.append(prerequisite)
    return missing


def _process_recovery_route(route: str, state: dict[str, Any]) -> tuple[str, str]:
    if route == "modeling":
        if state.get("missing_information"):
            return "discovery", "process.discovery"
        return "evidence", "process.evidence"
    if route == "delegate_canvas":
        if _has_canonical_semantic_model(state) and not state.get("missing_information"):
            return "modeling", "process.modeling"
        return "evidence", "process.evidence"
    return "clarification", "process.clarification"


def authorize_routing_decision(
    *,
    owner: Owner,
    decision: RoutingDecisionBase,
    state: dict[str, Any] | None = None,
    parse_source: str,
    parse_error: str | None,
) -> dict[str, Any]:
    state = state or {}
    proposed_route = str(getattr(decision, "route"))
    capability_id = decision.suggested_capability or DEFAULT_CAPABILITY_BY_OWNER_ROUTE.get((owner, proposed_route))
    status = "authorized"
    blocking_conditions = [*decision.blocking_conditions]
    route = proposed_route
    termination_reason = None

    if parse_error and parse_source != "router_recovery_direct":
        status = "invalid_structured_decision"
        route = "clarification"
        capability_id = f"{owner}.clarification"
        blocking_conditions.append(parse_error)
        termination_reason = "WAITING_FOR_USER"
    elif parse_error:
        status = "router_recovery_direct"

    if decision.needs_clarification or proposed_route == "clarification":
        status = "clarification_required" if status == "authorized" else status
        route = "clarification"
        capability_id = f"{owner}.clarification"
        termination_reason = "WAITING_FOR_USER"

    spec = CAPABILITY_REGISTRY.get(capability_id or "")
    if spec is None:
        status = "unregistered_capability"
        route = "clarification"
        capability_id = f"{owner}.clarification"
        spec = CAPABILITY_REGISTRY[capability_id]
        blocking_conditions.append(f"Capability is not registered: {decision.suggested_capability}")
        termination_reason = "WAITING_FOR_USER"
    elif spec.owner != owner or spec.route != route:
        status = "capability_route_mismatch"
        route = "clarification"
        capability_id = f"{owner}.clarification"
        spec = CAPABILITY_REGISTRY[capability_id]
        blocking_conditions.append("Suggested capability does not match the authorized owner/route.")
        termination_reason = "WAITING_FOR_USER"

    missing = missing_prerequisites(
        spec,
        {
            **state,
            "entity_hints": decision.entity_hints,
            "workflow_scope": getattr(decision, "workflow_scope", None),
        },
    )
    if missing:
        blocking_conditions.extend(f"Missing prerequisite: {item}" for item in missing)
        if owner == "process":
            route, capability_id = _process_recovery_route(proposed_route, state)
            spec = CAPABILITY_REGISTRY[capability_id]
            status = "state_constrained_reroute"
            termination_reason = None
        else:
            route = "clarification"
            capability_id = f"{owner}.clarification"
            spec = CAPABILITY_REGISTRY[capability_id]
            status = "missing_prerequisite"
            termination_reason = "WAITING_FOR_USER"

    target = spec.target
    return {
        "route": route,
        "proposed_route": proposed_route,
        "target": target,
        "status": status,
        "proposed_capability": decision.suggested_capability,
        "authorized_capability": capability_id,
        "blocking_conditions": blocking_conditions,
        "termination_reason": termination_reason,
        "parse_source": parse_source,
        "parse_error": parse_error,
    }
