from __future__ import annotations

import json
from typing import Any, Literal

from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from backend.llm_streaming import stream_to_final


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
    # The engineering-loop budget is deliberately NOT a field here. CODE_QUALITY.md
    # ("Runtime MUST own arithmetic, limits, deadlines, budgets") puts limits on the
    # runtime side of the boundary, and a model-set ceiling broke that both ways: a
    # value of 1 could truncate a full_workflow after one pass, and the router
    # rewrote the budget on every re-entry. The runtime owns it now
    # (ENGINEERING_LOOP_MAX_ITERATIONS); the agent still decides when to stop, by
    # setting workflow_scope and route.

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
    # What the canvas should look like once the request is satisfied. The agent
    # declares the target end state; the runtime only verifies it deterministically.
    # An emptied canvas cannot be checked against the semantic model - there is
    # nothing left to compare - so it needs its own completion check.
    expected_canvas_outcome: Literal["updated_model", "empty_canvas"] = "updated_model"

    @model_validator(mode="after")
    def normalize_route_clarification(self):
        """Synchronize clarification state when the route is ``"clarification"``.
        
        When applicable, enables clarification mode and sets the workflow scope to
        ``"clarification"``. Mutates and returns the current routing decision without
        performing persistence.
        
        Returns:
            The current routing decision.
        """
        if self.route == "clarification":
            self.needs_clarification = True
            self.canvas_mode = "clarification"
            self.workflow_scope = "clarification"
        return self


ALL_CHAT_MODES: frozenset[str] = frozenset({"plan", "edit", "agent"})


class CapabilitySpec(BaseModel):
    id: str
    owner: Owner
    route: str
    target: str | None = None
    prerequisites: list[str] = Field(default_factory=list)
    description: str = ""
    # Chat modes this capability is available in. `agent` is the full loop and is
    # in every set; `plan` understands and proposes without changing the process
    # model; `edit` applies the change asked for without re-planning it.
    modes: frozenset[str] = ALL_CHAT_MODES


CAPABILITY_REGISTRY: dict[str, CapabilitySpec] = {
    "consultant.direct": CapabilitySpec(
        id="consultant.direct",
        owner="consultant",
        route="direct",
        description=(
            "Consultant-level strategy, memory, planning, positioning, offers, "
            "cross-project synthesis or general advice."
        ),
    ),
    "consultant.home": CapabilitySpec(
        id="consultant.home",
        owner="consultant",
        route="home",
        target="home_subgraph",
        description="Home dashboard overview, priorities, risks, recent activity or next actions.",
    ),
    "consultant.clients": CapabilitySpec(
        id="consultant.clients",
        owner="consultant",
        route="clients",
        target="clients_subgraph",
        description="Client record work: listing, creating, checking or maintaining clients.",
    ),
    "consultant.setup": CapabilitySpec(
        id="consultant.setup",
        owner="consultant",
        route="setup",
        target="setup_subgraph",
        description=(
            "Explicit initial workspace setup involving a client plus a project, "
            "process stub, source or decision."
        ),
    ),
    "consultant.project_delegation": CapabilitySpec(
        id="consultant.project_delegation",
        owner="consultant",
        route="delegate_project",
        target="project_macro",
        description=(
            "Project execution, status, sources, decisions, deliverables, phase, "
            "progress or next step."
        ),
    ),
    "consultant.process_delegation": CapabilitySpec(
        id="consultant.process_delegation",
        owner="consultant",
        route="delegate_process",
        target="process_macro",
        description=(
            "AS-IS/TO-BE discovery, process analysis, evidence synthesis, readiness "
            "or BPMN semantic review."
        ),
    ),
    "consultant.canvas_delegation": CapabilitySpec(
        id="consultant.canvas_delegation",
        owner="consultant",
        route="delegate_canvas",
        target="canvas_macro",
        description="BPMN XML, canvas inspection, canvas edits, validation, layout, versions or approval.",
    ),
    "consultant.clarification": CapabilitySpec(
        id="consultant.clarification",
        owner="consultant",
        route="clarification",
        description="Context, owner or entity reference is ambiguous.",
    ),
    "project.direct": CapabilitySpec(
        id="project.direct",
        owner="project",
        route="direct",
        description=(
            "Project-level discussion, project context retrieval, project evidence or "
            "interview saving and retrieval, project-scoped GraphRAG, light synthesis, "
            "scope clarification, source/decision awareness or general project coordination."
        ),
    ),
    "project.delivery": CapabilitySpec(
        id="project.delivery",
        owner="project",
        route="delivery",
        target="delivery_subgraph",
        description=(
            "Phase, progress, milestones, deliverables, risks, blockers, next step, "
            "weekly plan or project status update."
        ),
    ),
    "project.process_coordination": CapabilitySpec(
        id="project.process_coordination",
        owner="project",
        route="process_coordination",
        target="process_coordination_subgraph",
        prerequisites=["existing_project_process"],
        description=(
            "Multiple processes in one project: sequencing, readiness matrix, "
            "cross-process dependencies, interview needs by process or handoff planning. "
            "Needs processes that already exist: a project with none has nothing to coordinate."
        ),
    ),
    "project.process_delegation": CapabilitySpec(
        id="project.process_delegation",
        owner="project",
        route="delegate_process",
        target="process_macro",
        prerequisites=["existing_project_process", "unambiguous_process_target"],
        description=(
            "Deep work on one process that is already registered in this project: "
            "AS-IS/TO-BE discovery, evidence synthesis, readiness or BPMN semantic "
            "review. Needs one unambiguous target process that exists. Creating the "
            "process record is project work, not a reason to delegate."
        ),
    ),
    "project.canvas_delegation": CapabilitySpec(
        id="project.canvas_delegation",
        owner="project",
        route="delegate_canvas",
        target="canvas_macro",
        prerequisites=["existing_project_process", "unambiguous_process_target"],
        description="Hand the canvas of one unambiguous existing process over to the Canvas Macro Agent.",
    ),
    "project.clarification": CapabilitySpec(
        id="project.clarification",
        owner="project",
        route="clarification",
        description="The project or the target process is ambiguous.",
    ),
    "process.direct": CapabilitySpec(
        id="process.direct",
        owner="process",
        route="direct",
        description=(
            "Process-level discussion, retrieval of existing context, light explanation "
            "or scope clarification the Process Macro Agent can answer itself."
        ),
    ),
    "process.discovery": CapabilitySpec(
        id="process.discovery",
        owner="process",
        route="discovery",
        target="discovery_subgraph",
        prerequisites=["process_id"],
        description=(
            "Process boundaries, trigger, start/end, stakeholders, official vs actual "
            "process, missing knowledge, interview planning or discovery readiness."
        ),
        modes=frozenset({"plan", "agent"}),
    ),
    "process.evidence": CapabilitySpec(
        id="process.evidence",
        owner="process",
        route="evidence",
        target="evidence_subgraph",
        prerequisites=["process_id"],
        description=(
            "Source saving and custody, claim extraction, confidence, contradictions, "
            "evidence coverage, hypotheses or open questions."
        ),
        modes=frozenset({"plan", "agent"}),
    ),
    "process.modeling": CapabilitySpec(
        id="process.modeling",
        owner="process",
        route="modeling",
        target="modeling_subgraph",
        prerequisites=["process_id", "process_understanding", "no_critical_contradictions"],
        description=(
            "ProcessUnderstanding, AS-IS review, BPMNSemanticModel, modeling readiness, "
            "semantic BPMN structure or review before canvas."
        ),
        modes=frozenset({"plan", "agent"}),
    ),
    "process.canvas_handoff": CapabilitySpec(
        id="process.canvas_handoff",
        owner="process",
        route="delegate_canvas",
        target="canvas_macro",
        prerequisites=["process_id", "bpmn_semantic_model", "readiness_for_canvas"],
        description=(
            "BPMN XML, canvas inspection, canvas edits, layout, validation, versions, "
            "approval or saved XML changes. Runs the Canvas Macro Agent on this process."
        ),
        modes=frozenset({"edit", "agent"}),
    ),
    "process.clarification": CapabilitySpec(
        id="process.clarification",
        owner="process",
        route="clarification",
        description="Process intent is unclear or required ids/context are missing.",
    ),
    "canvas.direct": CapabilitySpec(
        id="canvas.direct",
        owner="canvas",
        route="direct",
        description="Read-only canvas explanation, scope/context check or very light discussion.",
    ),
    "canvas.patch_edit": CapabilitySpec(
        id="canvas.patch_edit",
        owner="canvas",
        route="patch_edit",
        target="patch_edit_subgraph",
        prerequisites=["bpmn_model_id", "effective_bpmn_xml"],
        description=(
            "Local deterministic canvas edits with semantic and memory context available: "
            "label/documentation/owner/lane, add or remove one element, connect or "
            "reconnect a few elements, empty the canvas."
        ),
        modes=frozenset({"edit", "agent"}),
    ),
    "canvas.construction": CapabilitySpec(
        id="canvas.construction",
        owner="canvas",
        route="construction",
        target="construction_subgraph",
        prerequisites=["bpmn_model_id"],
        description=(
            "Generate, build, rebuild, redesign or substantially revise a canvas section "
            "from ProcessUnderstanding/BPMNSemanticModel/evidence, or prepare that semantic "
            "context from a substantive raw process description supplied by the user. "
            "Available even when no semantic context is loaded yet."
        ),
        # In every mode, because the *write* is what the mode governs and the write
        # guard already enforces it: plan mode can prepare and preview but not
        # apply, edit mode can apply a preview the user just approved. Blocking the
        # route in edit mode instead left a prepared preview impossible to apply -
        # "inseriscila nel canvas" came back as "what should I insert?".
        modes=ALL_CHAT_MODES,
    ),
    "canvas.layout": CapabilitySpec(
        id="canvas.layout",
        owner="canvas",
        route="layout",
        target="layout_subgraph",
        prerequisites=["bpmn_model_id", "effective_bpmn_xml"],
        description=(
            "Make the current canvas readable and ordered without changing business "
            "semantics: spacing, row wrapping, lane sizing, labels, annotations, data "
            "objects and edge routing."
        ),
        modes=frozenset({"edit", "agent"}),
    ),
    "canvas.validation": CapabilitySpec(
        id="canvas.validation",
        owner="canvas",
        route="validation",
        target="validation_subgraph",
        prerequisites=["bpmn_model_id", "effective_bpmn_xml"],
        description=(
            "Validate XML, semantic coverage, traceability, layout quality and "
            "gateway/lane/path correctness without mutating the model."
        ),
    ),
    "canvas.clarification": CapabilitySpec(
        id="canvas.clarification",
        owner="canvas",
        route="clarification",
        description="Required ids/context or the scope of the requested change is unclear.",
    ),
}


def capabilities_for(owner: Owner, mode: str | None = None) -> list[CapabilitySpec]:
    """Lists capabilities available to an owner, optionally filtered by chat mode.
    
    Args:
        owner: The capability owner.
        mode: Untrusted chat-mode value used to filter capabilities. When omitted,
            capabilities for all chat modes are included.
    
    Returns:
        The matching capability specifications, or an empty list when none are
        available.
    """
    return [
        spec
        for spec in CAPABILITY_REGISTRY.values()
        if spec.owner == owner and (mode is None or mode in spec.modes)
    ]


def capability_menu(owner: Owner, mode: str | None = None) -> str:
    """Render the registry-authorized capabilities available to an owner and chat mode.
    
    Args:
        owner (Owner): Untrusted owner value used to select capabilities.
        mode (str | None): Untrusted chat-mode value used to filter capabilities. If
            omitted, capabilities are not filtered by mode.
    
    Returns:
        str: A newline-separated capability menu, including routes, identifiers,
            prerequisites, and descriptions where available.
    
    The function has no side effects or persistence behavior.
    """
    lines = []
    for spec in capabilities_for(owner, mode):
        line = f"- {spec.route} (capability: {spec.id})"
        if spec.prerequisites:
            line += f" [requires: {', '.join(spec.prerequisites)}]"
        if spec.description:
            line += f"\n  {spec.description}"
        lines.append(line)
    return "\n".join(lines)


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
        response = stream_to_final(structured_llm, messages, config=config)
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
    return stream_to_final(structured_llm, [instruction, *messages], config=config)


BLOCKING_CONTRADICTION_SEVERITIES = frozenset({"critical", "blocking", "high"})
CLEARING_CONTRADICTION_RESOLUTIONS = frozenset({"resolved", "not_material"})
DEFAULT_MINIMUM_READINESS_SCORE = 7

# Runtime-owned engineering-loop budget. Server policy, not a model field: the
# agent decides when the work is done, the runtime decides how long it may take.
ENGINEERING_LOOP_MAX_ITERATIONS = 6


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

        # Fold on the stable contradiction_id the tool emits; title is only a
        # fallback for older records. An unidentifiable contradiction gets its own
        # key and stays open - it can never be silently cleared.
        key = (
            _normalized(record.get("contradiction_id"))
            or _normalized(record.get("title") or record.get("id"))
            or f"__unidentified__{index}"
        )
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


def _normalized(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def _classified_gaps(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        gap
        for gap in state.get("process_gaps") or []
        if isinstance(gap, dict) and gap.get("severity")
    ]


def _has_blocking_gap(state: dict[str, Any]) -> bool:
    return any(
        _normalized(gap.get("severity")) == "blocking" for gap in _classified_gaps(state)
    )


def uncovered_missing_information(state: dict[str, Any]) -> list[str]:
    """Open items that no classified gap accounts for.

    A non-blocking gap covers only the entry it actually names - matched on the
    gap's own `missing_information` text or its title. Anything left unmatched
    keeps blocking: one gap the agent called non-blocking must not vouch for
    open items nobody has classified, which is how "any classification at all
    suppresses the whole list" would have let an unresolved approval authority
    through behind a cosmetic naming gap.
    """
    covered: set[str] = set()
    for gap in _classified_gaps(state):
        if _normalized(gap.get("severity")) == "blocking":
            continue
        for field in ("missing_information", "title"):
            key = _normalized(gap.get(field))
            if key:
                covered.add(key)

    return [
        item
        for item in state.get("missing_information") or []
        if _normalized(item) not in covered
    ]


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
    """Determine whether the state contains a complete canonical semantic model.
    
    Args:
        state (dict[str, Any]): Untrusted routing state to inspect.
    
    Returns:
        bool: `True` if the semantic model contains non-empty ``flowNodes``,
            ``sequenceFlows``, ``compilationPlan``, and
            ``sourceProcessUnderstanding`` sections, `False` otherwise.
    
    This function does not modify or persist state and does not raise errors for
    missing or malformed semantic-model data.
    """
    semantic_model = _state_value_as_dict(
        state.get("bpmn_semantic_model")
    )
    return bool(
        semantic_model.get("flowNodes")
        and semantic_model.get("sequenceFlows")
        and semantic_model.get("compilationPlan")
        and semantic_model.get("sourceProcessUnderstanding")
    )


def project_processes(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Return dictionary-valued project processes from routing state.
    
    Args:
        state (dict[str, Any]): Untrusted routing state containing an optional
            ``project_processes`` collection.
    
    Returns:
        list[dict[str, Any]]: The project process entries that are dictionaries.
        Returns an empty list when the collection is missing, null, or empty.
    
    This function does not modify or persist state and does not raise errors.
    """
    return [
        process
        for process in state.get("project_processes") or []
        if isinstance(process, dict)
    ]


def resolved_project_process(state: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve the unambiguous existing process targeted by the project state.
    
    Args:
        state (dict[str, Any]): Untrusted routing state containing project processes
            and an optional process entity hint.
    
    Returns:
        dict[str, Any] | None: The matching existing process, the sole project
        process when no hint is provided, or `None` when no unambiguous existing
        process can be identified.
    
    This function does not raise errors, mutate state, or persist data.
    """
    processes = project_processes(state)
    hint = _normalized((state.get("entity_hints") or {}).get("process"))

    if hint:
        for process in processes:
            if hint in {_normalized(process.get("id")), _normalized(process.get("name"))}:
                return process
        return None

    return processes[0] if len(processes) == 1 else None


def missing_prerequisites(spec: CapabilitySpec, state: dict[str, Any]) -> list[str]:
    """
    Identify prerequisites declared by a capability that are not satisfied by the current routing state.
    
    Args:
        spec (CapabilitySpec): Capability whose prerequisite requirements are evaluated.
        state (dict[str, Any]): Untrusted routing and workflow state used to assess prerequisite satisfaction.
    
    Returns:
        list[str]: Names of unmet prerequisites, preserving the order declared by the capability.
    
    This function is read-only and performs no persistence or other side effects.
    """
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
            elif _has_blocking_gap(state) or uncovered_missing_information(state):
                # A gap the agent called non-blocking excuses the item it names,
                # and nothing else: a blocking gap always blocks, and any open
                # item still unaccounted for keeps the canvas closed.
                missing.append(prerequisite)
        elif prerequisite == "no_critical_contradictions" and _has_critical_contradiction(state):
            missing.append(prerequisite)
        elif prerequisite == "existing_project_process" and not project_processes(state):
            missing.append(prerequisite)
        elif prerequisite == "unambiguous_process_target" and resolved_project_process(state) is None:
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


def authorize_routing_decision(
    *,
    owner: Owner,
    decision: RoutingDecisionBase,
    state: dict[str, Any] | None = None,
    parse_source: str,
    parse_error: str | None,
) -> dict[str, Any]:
    """
    Authorize a proposed routing decision against the capability registry and current workflow state.
    
    Args:
        owner: Expected owner of the proposed route.
        decision: Untrusted routing decision to validate and authorize.
        state: Untrusted workflow state used to evaluate chat-mode availability and prerequisites.
        parse_source: Source of the parsed routing decision.
        parse_error: Parsing or validation error associated with the decision, if any.
    
    Returns:
        A dictionary containing the authorized or clarification route, capability, status,
        blocking conditions, missing prerequisites, refused route, termination reason, and
        parsing metadata.
    
    The function performs no persistence or other external side effects. It converts
    invalid, unavailable, mismatched, or prerequisite-blocked decisions into clarification
    results rather than raising exceptions.
    """
    state = state or {}
    proposed_route = str(getattr(decision, "route"))
    capability_id = decision.suggested_capability or DEFAULT_CAPABILITY_BY_OWNER_ROUTE.get((owner, proposed_route))
    status = "authorized"
    blocking_conditions = [*decision.blocking_conditions]
    route = proposed_route
    termination_reason = None
    refused_route = None

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

    chat_mode = state.get("chat_mode")
    if chat_mode and chat_mode not in spec.modes:
        # The user chose how much of the workflow to hand over this turn. Like a
        # missing prerequisite this is a refusal with a reason, not a substitution:
        # `resolve_routing_decision` lets the agent pick something the mode allows.
        blocking_conditions.append(
            f"Capability {spec.id} is not available in {chat_mode} mode "
            f"(available in: {', '.join(sorted(spec.modes))})"
        )
        route = "clarification"
        capability_id = f"{owner}.clarification"
        spec = CAPABILITY_REGISTRY[capability_id]
        status = "capability_not_in_mode"
        termination_reason = "WAITING_FOR_USER"
        refused_route = proposed_route
    else:
        refused_route = None

    missing = missing_prerequisites(
        spec,
        {
            **state,
            "entity_hints": decision.entity_hints,
            "workflow_scope": getattr(decision, "workflow_scope", None),
        },
    )
    if missing:
        # The runtime refuses the capability and says why; it does not pick the
        # replacement work. Which alternative is right - gather evidence, run
        # discovery, ask the user - depends on the process, and that judgment
        # belongs to the agent. `resolve_routing_decision` hands these conditions
        # back to the router for one re-decision; clarification is only where the
        # turn lands if the agent cannot find an authorized route.
        blocking_conditions.extend(f"Missing prerequisite: {item}" for item in missing)
        route = "clarification"
        capability_id = f"{owner}.clarification"
        spec = CAPABILITY_REGISTRY[capability_id]
        status = "missing_prerequisite"
        termination_reason = "WAITING_FOR_USER"
        refused_route = proposed_route

    target = spec.target
    return {
        "route": route,
        "proposed_route": proposed_route,
        "target": target,
        "status": status,
        "proposed_capability": decision.suggested_capability,
        "authorized_capability": capability_id,
        "blocking_conditions": blocking_conditions,
        "missing_prerequisites": missing,
        "refused_route": refused_route,
        "termination_reason": termination_reason,
        "parse_source": parse_source,
        "parse_error": parse_error,
    }


# One re-decision after a refusal. The budget is runtime policy: without a bound
# a router that keeps proposing a blocked capability would loop on the model's
# account, and one informed retry is what "you were refused, here is why" buys.
ROUTER_REPLAN_ATTEMPTS = 1


def resolve_routing_decision(
    *,
    owner: Owner,
    llm,
    model: type[RoutingDecisionBase],
    messages: list[BaseMessage],
    config: RunnableConfig,
    invalid_factory,
    state: dict[str, Any] | None = None,
) -> tuple[RoutingDecisionBase, str, str | None]:
    """Resolve and authorize a routing decision, retrying once when runtime checks reject it.
    
    The retry is limited to missing prerequisites or chat-mode-incompatible capabilities.
    Other authorization outcomes, including clarification decisions, are returned without
    additional replanning. The function invokes the language model and does not persist
    state.
    
    Args:
        owner: Routing owner whose capabilities are authorized.
        llm: Language model used to produce routing decisions.
        model: Routing decision model to parse and validate.
        messages: Untrusted input messages supplied to the router.
        config: Invocation configuration for the language model.
        invalid_factory: Factory for invalid decisions produced during parsing.
        state: Untrusted runtime state used to determine chat mode and prerequisites.
    
    Returns:
        A tuple containing the final routing decision, its parse source, and any parse
        error. The decision may be a clarification decision when routing fails or remains
        unauthorized.
    """
    chat_mode = (state or {}).get("chat_mode")
    decision, parse_source, parse_error = invoke_structured_router(
        llm,
        model,
        messages,
        config=config,
        invalid_factory=invalid_factory,
    )

    for _ in range(ROUTER_REPLAN_ATTEMPTS):
        authorization = authorize_routing_decision(
            owner=owner,
            decision=decision,
            state=state,
            parse_source=parse_source,
            parse_error=parse_error,
        )
        if authorization["status"] not in {"missing_prerequisite", "capability_not_in_mode"}:
            break

        if authorization["status"] == "missing_prerequisite":
            refused_because = (
                "Unsatisfied prerequisites (verified against current state, not opinion): "
                f"{', '.join(authorization['missing_prerequisites'])}"
            )
            what_to_do = (
                "Either propose a capability whose prerequisites the current state "
                "already satisfies - typically the work that would produce the missing "
                "prerequisite - or route to clarification if only the user can unblock this."
            )
        else:
            refused_because = (
                f"The user put this chat in {chat_mode} mode, and that capability is not "
                "part of it. The mode is the user's choice about how much of the workflow "
                "to hand over; it is not yours to widen."
            )
            what_to_do = (
                "Propose a capability the mode does allow, or route to clarification and "
                "tell the user which mode would let you do what they asked."
            )

        refusal = SystemMessage(
            content=(
                "The runtime refused your previous routing decision.\n"
                f"Refused route: {authorization['refused_route']}\n"
                f"Refused capability: {authorization['proposed_capability']}\n"
                f"{refused_because}\n\n"
                f"Decide again. {what_to_do} Do not repeat the refused capability.\n\n"
                "Capabilities available to you:\n"
                f"{capability_menu(owner, chat_mode)}"
            )
        )
        decision, parse_source, parse_error = invoke_structured_router(
            llm,
            model,
            [*messages, refusal],
            config=config,
            invalid_factory=invalid_factory,
        )

    return decision, parse_source, parse_error
