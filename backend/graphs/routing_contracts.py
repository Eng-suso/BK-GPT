from __future__ import annotations

import json
from typing import Any, Literal

from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from backend.llm_streaming import stream_to_final


Owner = Literal["consultant", "project", "process", "canvas"]
WorkflowScope = Literal["direct", "local_operation", "single_step", "full_workflow", "clarification"]

# Quale artefatto la richiesta modifica. Erano due operazioni distinte trattate
# come una sola: "mettilo nel piano" e "genera il BPMN" competevano per la stessa
# decisione di routing senza che niente, nel runtime, distinguesse l'artefatto
# toccato. Il risultato era che una modifica al piano chiedeva la modalita' che
# serve a disegnare, per un'operazione che il disegno non lo tocca nemmeno.
#
# Il modello dichiara l'artefatto; il runtime verifica che la route sia coerente
# con l'artefatto dichiarato. La classificazione dell'intento resta lavoro del
# modello, l'accoppiamento fra le due operazioni no.
ArtifactTarget = Literal["modeling_plan", "bpmn_canvas", "none"]

ARTIFACT_TARGET_DESCRIPTION = """
target_artifact - quale artefatto questa richiesta modifica. Sono due, e sono
separati:

- modeling_plan: la comprensione strutturata del processo (partecipanti, corsie
  candidate, attivita', flusso, decisioni, percorsi di eccezione, evidenza a
  sostegno, incertezze, lacune, prontezza). "Mettilo nel piano", "aggiorna il
  piano", "aggiungi al piano", "correggi la review", "crea il piano con quello
  che sai". Si genera, si modifica, si versiona, si riapre e si approva SENZA
  toccare il diagramma.
- bpmn_canvas: il disegno. "Genera il BPMN", "applica al canvas", "disegnalo",
  "sposta questo nodo", "rinomina questo passaggio".
- none: la richiesta non modifica nessuno dei due (domanda, spiegazione,
  raccolta di evidenza, discovery).

Non accoppiarli. Una richiesta sul piano non e' una richiesta sul canvas, e
chiedere di passare alla modalita' che serve a disegnare per modificare il piano
e' una risposta sbagliata.
""".strip()


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
    # Il piano e il disegno sono due artefatti, e l'intento dell'utente decide
    # quale si tocca. Vedi ARTIFACT_TARGET_DESCRIPTION.
    target_artifact: ArtifactTarget = "none"
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
    # Il Canvas possiede il disegno e non possiede il piano: qui l'artefatto e'
    # dichiarato per lo stesso motivo per cui lo e' di la', cosi' una richiesta
    # sul piano arrivata fin qui si vede invece di essere eseguita sul diagramma.
    target_artifact: ArtifactTarget = "bpmn_canvas"
    # What the canvas should look like once the request is satisfied. The agent
    # declares the target end state; the runtime only verifies it deterministically.
    # An emptied canvas cannot be checked against the semantic model - there is
    # nothing left to compare - so it needs its own completion check.
    expected_canvas_outcome: Literal["updated_model", "empty_canvas"] = "updated_model"
    # Che tipo di costruzione e' questa. Serve al runtime per sapere se il
    # disegno si puo' produrre in modo deterministico dal piano - compilazione,
    # validazione, layout, salvataggio, senza un solo passaggio dal modello - o
    # se serve davvero un subagente. "Genera il BPMN" e "ridisegna solo il ramo
    # urgente" sono due operazioni diverse e costano due percorsi diversi.
    construction_kind: Literal[
        "full_from_plan", "partial_change", "from_user_description"
    ] = "full_from_plan"

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


WORKFLOW_CHAT_MODES: frozenset[str] = frozenset({"plan", "edit", "agent"})
ALL_CHAT_MODES: frozenset[str] = frozenset({"conversation", *WORKFLOW_CHAT_MODES})


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
    modes: frozenset[str] = WORKFLOW_CHAT_MODES
    # L'artefatto che questa capability puo' modificare. Serve al runtime per
    # rifiutare una route che non corrisponde all'artefatto dichiarato: senza
    # questo, "modifica il piano" e "disegna il BPMN" restano indistinguibili
    # per chiunque non sia il modello che le ha proposte.
    artifact: ArtifactTarget = "none"


CAPABILITY_REGISTRY: dict[str, CapabilitySpec] = {
    "consultant.direct": CapabilitySpec(
        id="consultant.direct",
        owner="consultant",
        route="direct",
        description=(
            "Consultant-level strategy, memory, planning, positioning, offers, "
            "cross-project synthesis or general advice."
        ),
        modes=ALL_CHAT_MODES,
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
            "Create the workspace records an engagement needs before anyone can work "
            "in it: a client, a project under a new or an already existing client, and "
            "optionally a first process stub, source or decision. 'Crea un progetto "
            "per <cliente>' belongs here, including when that client already exists."
        ),
    ),
    "consultant.project_delegation": CapabilitySpec(
        id="consultant.project_delegation",
        owner="consultant",
        route="delegate_project",
        target="project_macro",
        prerequisites=["existing_project"],
        description=(
            "Work inside a project that already exists: execution, status, sources, "
            "decisions, deliverables, phase, progress or next step. Creating the "
            "project record is not project work - a project that does not exist yet "
            "cannot be handed over, so that is setup."
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
        modes=ALL_CHAT_MODES,
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
        modes=ALL_CHAT_MODES,
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
        modes=ALL_CHAT_MODES,
    ),
    "process.direct": CapabilitySpec(
        id="process.direct",
        owner="process",
        route="direct",
        description=(
            "Process-level discussion, retrieval of existing context, light explanation "
            "or scope clarification the Process Macro Agent can answer itself."
        ),
        modes=ALL_CHAT_MODES,
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
            "Build or rebuild the modeling plan from scratch: ProcessUnderstanding, "
            "AS-IS review, BPMNSemanticModel, modeling readiness, semantic BPMN "
            "structure. Produces the plan; it does not draw the diagram. Use "
            "process.plan_edit instead when a plan already exists and the request "
            "adds to or corrects it."
        ),
        modes=frozenset({"plan", "agent"}),
        artifact="modeling_plan",
    ),
    "process.plan_edit": CapabilitySpec(
        id="process.plan_edit",
        owner="process",
        route="modeling",
        target="modeling_subgraph",
        # Nessun prerequisito di piano esistente: "crea il piano con quello che
        # sai" e "mettilo nel piano" sono la stessa operazione a due stadi
        # diversi dello stesso artefatto, e chiedere che il piano ci sia gia' per
        # poterlo scrivere e' il cerchio in cui il difetto viveva.
        prerequisites=["process_id"],
        description=(
            "Add to, correct, extend or version the modeling plan of this process "
            "WITHOUT touching the BPMN diagram: 'mettilo nel piano', 'aggiungi al "
            "piano', 'aggiorna il piano', 'crea il piano con quello che sai', "
            "'correggi la review'. The plan is a separate artifact from the canvas: "
            "it is generated, edited, versioned, reopened and approved on its own."
        ),
        modes=frozenset({"plan", "agent"}),
        artifact="modeling_plan",
    ),
    "process.canvas_handoff": CapabilitySpec(
        id="process.canvas_handoff",
        owner="process",
        route="delegate_canvas",
        target="canvas_macro",
        prerequisites=["process_id", "bpmn_semantic_model", "readiness_for_canvas"],
        description=(
            "Apply the plan to the DIAGRAM: BPMN XML, canvas inspection, canvas edits, "
            "layout, validation, versions, approval or saved XML changes. Runs the "
            "Canvas Macro Agent on this process. Editing the plan itself is not canvas "
            "work and does not belong here."
        ),
        modes=frozenset({"edit", "agent"}),
        artifact="bpmn_canvas",
    ),
    "process.clarification": CapabilitySpec(
        id="process.clarification",
        owner="process",
        route="clarification",
        description="Process intent is unclear or required ids/context are missing.",
        modes=ALL_CHAT_MODES,
    ),
    "canvas.direct": CapabilitySpec(
        id="canvas.direct",
        owner="canvas",
        route="direct",
        description="Read-only canvas explanation, scope/context check or very light discussion.",
        modes=ALL_CHAT_MODES,
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
        artifact="bpmn_canvas",
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
        # In every delegated workflow mode: plan can prepare and preview but not
        # apply, while conversation cannot start construction at all. The write
        # guard remains the second boundary: plan still cannot save, while edit
        # mode can apply a preview the user just approved. Blocking the
        # route in edit mode instead left a prepared preview impossible to apply -
        # "inseriscila nel canvas" came back as "what should I insert?".
        modes=WORKFLOW_CHAT_MODES,
        artifact="bpmn_canvas",
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
        artifact="bpmn_canvas",
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
        modes=ALL_CHAT_MODES,
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


# La scala delle modalita', dalla piu' stretta alla piu' larga. Ogni gradino
# permette cio' che permette il precedente, piu' qualcosa. Serve al runtime per
# dire *quale* modalita' sbloccherebbe un rifiuto: quando a sceglierla era il
# modello, per modificare il piano veniva chiesta la modalita' che serve a
# disegnare, e al consulente arrivava un cambio di modalita' che non gli serviva.
MODE_LADDER: tuple[str, ...] = ("conversation", "plan", "edit", "agent")

# Come la modalita' si chiama nel prodotto. Il consulente non legge `edit`.
MODE_LABEL_IT: dict[str, str] = {
    "conversation": "Conversazione",
    "plan": "Piano",
    "edit": "Modifica",
    "agent": "Agente",
}


def narrowest_mode_for(spec: CapabilitySpec) -> str | None:
    """La modalita' meno ampia in cui questa capability e' disponibile.

    Args:
        spec: La capability rifiutata.

    Returns:
        Il nome della modalita', o `None` se la capability non ne dichiara
        nessuna riconoscibile.
    """
    for mode in MODE_LADDER:
        if mode in spec.modes:
            return mode
    return None


def mode_label(mode: str | None) -> str:
    return MODE_LABEL_IT.get(str(mode or ""), str(mode or "sconosciuta"))


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
        if spec.artifact != "none":
            line += f" [modifies: {spec.artifact}]"
        if spec.prerequisites:
            line += f" [requires: {', '.join(spec.prerequisites)}]"
        if spec.description:
            line += f"\n  {spec.description}"
        lines.append(line)
    return "\n".join(lines)


# Quale capability vale quando il router propone una route senza nominarla. Con
# due capability sulla stessa route - il piano si costruisce e si modifica, e
# sono due operazioni diverse dello stesso artefatto - "l'ultima registrata
# vince" sceglieva a caso.
#
# Il default e' quella che pretende meno. Su `modeling` l'alternativa era
# `process.modeling`, che richiede `process_understanding`: una route proposta
# senza nome sarebbe caduta sulla capability che pretende il piano per poter
# scrivere il piano, ed e' esattamente il cerchio in cui il difetto viveva. Chi
# vuole la capability piu' esigente la nomina.
DEFAULT_CAPABILITY_BY_OWNER_ROUTE: dict[tuple[str, str], str] = {}
for _spec in sorted(CAPABILITY_REGISTRY.values(), key=lambda spec: len(spec.prerequisites)):
    DEFAULT_CAPABILITY_BY_OWNER_ROUTE.setdefault((_spec.owner, _spec.route), _spec.id)
del _spec


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


def _plan_is_synthesizable(state: dict[str, Any]) -> bool:
    """C'e' l'evidenza per costruire un piano, anche se il piano non c'e' ancora.

    Le due soglie del task sono queste, e vanno tenute separate: "abbastanza per
    una bozza vincolata all'evidenza" e "abbastanza per dichiarare l'AS-IS
    validato". Un processo con tre interviste e nessun piano sta sopra la prima e
    sotto la seconda; trattarlo come non modellabile cancella cio' che si sa gia'
    invece di trasformarlo in una bozza con le lacune dichiarate dentro.
    """
    draft_readiness = _state_value_as_dict(state.get("draft_readiness"))
    if draft_readiness.get("status") == "synthesizable":
        return True

    # Fallback per uno stato che non porta la readiness (un router invocato fuori
    # dal nodo di contesto): l'evidenza agli atti vale comunque.
    ledger = _state_value_as_dict(state.get("evidence_ledger"))
    return max(
        int(ledger.get("source_count") or 0), len(ledger.get("claims") or [])
    ) > 0


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


def workspace_projects(state: dict[str, Any]) -> list[dict[str, Any]]:
    """I progetti che il workspace contiene davvero, come li vede il router."""
    return [
        project
        for project in state.get("workspace_projects") or []
        if isinstance(project, dict)
    ]


def has_existing_project(state: dict[str, Any]) -> bool:
    """C'e' un progetto reale a cui la richiesta si riferisce?

    Il router puo' nominare un progetto (`entity_hints["project"]`) o un cliente:
    in entrambi i casi la verifica e' sui record, non sulla convinzione del
    modello. Quando il nome citato non corrisponde a nessun progetto registrato,
    non c'e' niente da delegare - il lavoro e' crearlo.
    """
    projects = workspace_projects(state)
    if not projects:
        return False

    hints = state.get("entity_hints") or {}
    project_hint = _normalized(hints.get("project"))
    client_hint = _normalized(hints.get("client"))

    if project_hint:
        return any(
            project_hint in {_normalized(project.get("id")), _normalized(project.get("name"))}
            for project in projects
        )

    if client_hint:
        return any(
            client_hint
            in {_normalized(project.get("client_id")), _normalized(project.get("client"))}
            for project in projects
        )

    return True


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
            if _plan_is_synthesizable(state):
                # Il piano non c'e' ancora, ma l'evidenza da cui costruirlo si'.
                # Rifiutare qui era il difetto: con tre interviste agli atti il
                # gate rispondeva "prerequisito mancante", il turno finiva in
                # chiarimento e al consulente arrivavano le domande da
                # questionario su trigger, attori e prima attivita'. Il confine
                # sintetizza il piano prima di consegnare al canvas.
                continue
            missing.append(prerequisite)
        elif prerequisite == "readiness_for_canvas":
            if state.get("workflow_scope") == "local_operation" and state.get("saved_bpmn_xml"):
                continue
            # Una lacuna che l'agente ha classificato bloccante chiude il canvas
            # comunque. Le due soglie sono due, ma "bloccante" e' la parola con
            # cui l'agente dice che senza quella risposta il disegno sarebbe una
            # invenzione: le scorciatoie qui sotto aprivano la porta anche a
            # quello, e una bozza con dentro una lacuna dichiarata bloccante non
            # e' una bozza onesta, e' un AS-IS inventato con una nota a margine.
            blocking_gap = _has_blocking_gap(state)
            draft_readiness = _state_value_as_dict(state.get("draft_readiness"))
            if (
                not blocking_gap
                and draft_readiness.get("status") == "modelable"
                and not (draft_readiness.get("blockers") or [])
            ):
                # A preliminary BPMN may carry explicit gaps. Final approval is
                # governed separately by validation_readiness/review status.
                continue
            # La scorciatoia "c'e' evidenza, il piano si puo' sintetizzare" vale
            # solo dove il piano non c'e'. Con un piano agli atti che si dichiara
            # non modellabile, contare le interviste per aprire comunque il
            # canvas ribalta il verdetto del piano con un conteggio di fonti: il
            # piano ha gia' guardato quelle fonti e ha detto di no.
            if (
                not blocking_gap
                and not _has_canonical_semantic_model(state)
                and _plan_is_synthesizable(state)
            ):
                continue
            if blocking_gap:
                missing.append(prerequisite)
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
        elif prerequisite == "existing_project" and not has_existing_project(state):
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

    # L'artefatto dichiarato e l'artefatto che la capability tocca devono essere
    # lo stesso. E' il punto in cui "mettilo nel piano" smetteva di essere una
    # modifica al piano e diventava una richiesta sul disegno: due operazioni
    # diverse su due artefatti diversi, e niente nel runtime le teneva separate.
    declared_artifact = getattr(decision, "target_artifact", "none")
    if (
        status == "authorized"
        and declared_artifact in {"modeling_plan", "bpmn_canvas"}
        and spec.artifact != "none"
        and spec.artifact != declared_artifact
    ):
        blocking_conditions.append(
            f"Artifact mismatch: the request was declared as modifying "
            f"{declared_artifact}, but {spec.id} modifies {spec.artifact}. "
            "The modeling plan and the BPMN canvas are two separate artifacts and "
            "one operation does not stand in for the other."
        )
        route = "clarification"
        capability_id = f"{owner}.clarification"
        spec = CAPABILITY_REGISTRY[capability_id]
        status = "artifact_route_mismatch"
        termination_reason = "WAITING_FOR_USER"
        refused_route = proposed_route

    chat_mode = state.get("chat_mode")
    required_mode = None
    if chat_mode and chat_mode not in spec.modes:
        # The user chose how much of the workflow to hand over this turn. Like a
        # missing prerequisite this is a refusal with a reason, not a substitution:
        # `resolve_routing_decision` lets the agent pick something the mode allows.
        #
        # *Quale* modalita' sbloccherebbe il rifiuto lo calcola il runtime, non il
        # modello: sceglierla a occhio faceva chiedere la modalita' che serve a
        # disegnare per un'operazione che il disegno non lo tocca.
        required_mode = narrowest_mode_for(spec)
        blocking_conditions.append(
            f"Capability {spec.id} is not available in {chat_mode} mode "
            f"(available in: {', '.join(sorted(spec.modes))}; narrowest mode that "
            f"allows it: {required_mode or 'none'})"
        )
        route = "clarification"
        capability_id = f"{owner}.clarification"
        spec = CAPABILITY_REGISTRY[capability_id]
        status = "capability_not_in_mode"
        termination_reason = "WAITING_FOR_USER"
        refused_route = proposed_route

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
        # Lo stato della modalita' viene da qui, non dalla conversazione: e' cio'
        # che il runtime ha applicato in questo turno. Un "si', fatto" dell'utente
        # non e' una fonte su quale modalita' e' attiva.
        "active_chat_mode": chat_mode,
        "required_mode": required_mode,
        "declared_artifact": declared_artifact,
        "capability_artifact": spec.artifact,
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
        if authorization["status"] not in {
            "missing_prerequisite",
            "capability_not_in_mode",
            "artifact_route_mismatch",
        }:
            break

        if authorization["status"] == "artifact_route_mismatch":
            refused_because = (
                f"You declared this request as modifying {authorization['declared_artifact']}, "
                f"then proposed a capability that modifies {authorization['capability_artifact']}. "
                "The modeling plan and the BPMN canvas are two artifacts with two "
                "separate lifecycles: editing the plan does not draw anything, and "
                "drawing does not rewrite the plan."
            )
            what_to_do = (
                "Decide which artifact the user actually asked you to change, then "
                "propose the capability that owns that artifact."
            )
        elif authorization["status"] == "missing_prerequisite":
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
            required = authorization.get("required_mode")
            refused_because = (
                f"The chat is in {chat_mode} mode (this is the runtime's record of the "
                "mode, not something inferred from the conversation), and that "
                "capability is not part of it. The mode is the user's choice about how "
                "much of the workflow to hand over; it is not yours to widen."
            )
            what_to_do = (
                "Propose a capability the mode does allow, or route to clarification. "
                + (
                    f"If you tell the user to switch, the mode they need is "
                    f"'{required}' ({mode_label(required)}) - the narrowest one that "
                    "allows what they asked. Do not name a wider mode than that, and "
                    "do not ask for a canvas mode to edit the plan."
                    if required
                    else "Do not invent a mode name."
                )
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
