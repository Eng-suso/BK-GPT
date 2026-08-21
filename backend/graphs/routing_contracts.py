from __future__ import annotations

from typing import Any, Literal

from langchain_core.messages import BaseMessage
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
    max_iterations: int = Field(default=2, ge=1, le=5)

    @model_validator(mode="after")
    def normalize_route_clarification(self):
        if self.route == "clarification":
            self.needs_clarification = True
            self.process_mode = "clarification"
            self.workflow_scope = "clarification"
        return self


class CanvasRoutingDecision(RoutingDecisionBase):
    owner: Literal["canvas"] = "canvas"
    route: Literal["direct", "patch_edit", "construction", "validation", "clarification"] = "direct"
    canvas_mode: Literal["inspection", "patch_edit", "construction", "validation", "clarification"] | None = None
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
        prerequisites=["bpmn_model_id", "canvas_semantic_context"],
        description="Build or rebuild canvas sections from process semantic context and traceability memory.",
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
        structured_llm = llm.with_structured_output(model)
        response = structured_llm.invoke(messages, config=config)
        return parse_routing_decision(response, model, invalid_factory)
    except Exception as exc:
        reason = f"Structured router failed: {type(exc).__name__}"
        return invalid_factory(reason), "invalid", reason


def _has_critical_contradiction(state: dict[str, Any]) -> bool:
    for contradiction in state.get("contradictions") or []:
        if not isinstance(contradiction, dict):
            continue
        severity = str(contradiction.get("severity") or contradiction.get("impact") or "").lower()
        if severity in {"critical", "blocking", "high"}:
            return True
    return False


def missing_prerequisites(spec: CapabilitySpec, state: dict[str, Any]) -> list[str]:
    missing = []
    for prerequisite in spec.prerequisites:
        if prerequisite == "process_id" and not (state.get("process_id") or (state.get("entity_hints") or {}).get("process")):
            missing.append(prerequisite)
        elif prerequisite == "process_understanding" and not state.get("process_understanding_json"):
            missing.append(prerequisite)
        elif prerequisite == "bpmn_semantic_model" and not state.get("bpmn_semantic_model_json"):
            if state.get("workflow_scope") == "local_operation" and state.get("saved_bpmn_xml"):
                continue
            missing.append(prerequisite)
        elif prerequisite == "readiness_for_canvas":
            if state.get("workflow_scope") == "local_operation" and state.get("saved_bpmn_xml"):
                continue
            readiness = state.get("readiness_score")
            if readiness is None or readiness < 7 or state.get("missing_information"):
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
        elif prerequisite == "canvas_semantic_context" and not (
            state.get("process_understanding_json")
            or state.get("bpmn_semantic_model_json")
            or state.get("process_understanding")
            or state.get("bpmn_semantic_model")
        ):
            missing.append(prerequisite)
    return missing


def _process_recovery_route(route: str, state: dict[str, Any]) -> tuple[str, str]:
    if route == "modeling":
        if state.get("missing_information"):
            return "discovery", "process.discovery"
        return "evidence", "process.evidence"
    if route == "delegate_canvas":
        if state.get("process_understanding_json") and not state.get("missing_information"):
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

    if parse_error:
        status = "invalid_structured_decision"
        route = "clarification"
        capability_id = f"{owner}.clarification"
        blocking_conditions.append(parse_error)
        termination_reason = "WAITING_FOR_USER"

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
