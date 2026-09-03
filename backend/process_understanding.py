from __future__ import annotations

import json
from functools import lru_cache
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from backend.llm_config import chat_openai_kwargs
from backend.settings import settings


class ProcessActor(BaseModel):
    id: str
    label: str
    kind: Literal["person", "role", "team", "organization", "system", "external_party"]
    source_evidence: list[str] = Field(default_factory=list)


class ProcessEvent(BaseModel):
    id: str
    label: str
    type: Literal["start", "end", "timer", "message", "exception"]
    timing: str | None = None
    source_evidence: list[str] = Field(default_factory=list)


class ProcessStep(BaseModel):
    id: str
    label: str
    description: str | None = None
    actor_ids: list[str] = Field(default_factory=list)
    type: Literal[
        "user_task",
        "manual_task",
        "service_task",
        "send_task",
        "receive_task",
        "business_rule_task",
        "script_task",
        "subprocess",
    ] = "user_task"
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    source_evidence: list[str] = Field(default_factory=list)


class ProcessHandoff(BaseModel):
    id: str
    from_actor_id: str | None = None
    to_actor_id: str | None = None
    artifact: str | None = None
    trigger: str | None = None
    source_evidence: list[str] = Field(default_factory=list)


class ProcessDataObject(BaseModel):
    id: str
    label: str
    kind: Literal["document", "form", "record", "payment", "receipt", "notification", "data", "other"] = "data"
    source_evidence: list[str] = Field(default_factory=list)


class ProcessParticipant(BaseModel):
    id: str
    label: str
    actor_id: str | None = None
    kind: Literal[
        "individual",
        "role",
        "organization",
        "public_authority",
        "system",
        "channel",
        "other",
    ]
    responsibility: Literal[
        "initiator",
        "executor",
        "intermediary",
        "decision_owner",
        "service_provider",
        "system_of_record",
        "recipient",
        "other",
    ] = "other"
    bpmn_container: Literal["pool", "lane", "black_box", "out_of_scope"]
    parent_pool_id: str | None = None
    rationale: str | None = None
    source_evidence: list[str] = Field(default_factory=list)


class ProcessDocumentRequirement(BaseModel):
    id: str
    label: str
    data_object_id: str | None = None
    required_when: str | None = None
    provided_by_actor_id: str | None = None
    received_by_actor_id: str | None = None
    validation_owner_actor_id: str | None = None
    mandatory: bool | None = None
    source_evidence: list[str] = Field(default_factory=list)


class ProcessBusinessRule(BaseModel):
    id: str
    label: str
    condition: str | None = None
    consequence: str
    applies_to_ids: list[str] = Field(default_factory=list)
    certainty: Literal["explicit", "inferred", "assumption"] = "explicit"
    source_evidence: list[str] = Field(default_factory=list)


class ProcessFlowEdge(BaseModel):
    id: str
    source_id: str
    target_id: str
    label: str
    condition: str | None = None
    kind: Literal["sequence", "message", "temporal", "data"] = "sequence"
    path_id: str | None = None
    source_evidence: list[str] = Field(default_factory=list)


class ProcessDecisionOutcome(BaseModel):
    id: str
    label: str
    condition: str | None = None
    target_ref: str | None = None
    target_path_id: str | None = None
    rejoins_at: str | None = None
    ends_process: bool = False
    is_default: bool = False
    certainty: Literal["explicit", "inferred", "assumption"] = "explicit"
    source_evidence: list[str] = Field(default_factory=list)


class ProcessControl(BaseModel):
    id: str
    label: str
    control_type: Literal[
        "eligibility",
        "document_completeness",
        "document_correctness",
        "approval",
        "timing",
        "compliance",
        "business_rule",
        "other",
    ] = "other"
    checked_item: str
    control_owner_actor_id: str | None = None
    subject_ids: list[str] = Field(default_factory=list)
    pass_condition: str | None = None
    fail_condition: str | None = None
    pass_target_ref: str | None = None
    fail_target_ref: str | None = None
    source_evidence: list[str] = Field(default_factory=list)


class BpmnPoolCandidate(BaseModel):
    id: str
    label: str
    participant_id: str | None = None
    actor_ids: list[str] = Field(default_factory=list)
    is_external: bool = False
    rendering_intent: Literal["expanded", "black_box", "out_of_scope"] = "expanded"
    rationale: str | None = None


class BpmnLaneCandidate(BaseModel):
    id: str
    label: str
    pool_id: str
    participant_id: str | None = None
    actor_ids: list[str] = Field(default_factory=list)
    role: str | None = None
    rationale: str | None = None


class BpmnMessageFlowCandidate(BaseModel):
    id: str
    label: str
    from_participant_id: str | None = None
    to_participant_id: str | None = None
    from_actor_id: str | None = None
    to_actor_id: str | None = None
    source_ref: str | None = None
    target_ref: str | None = None
    artifact: str | None = None
    trigger: str | None = None
    source_evidence: list[str] = Field(default_factory=list)


class BpmnParticipantTopology(BaseModel):
    pools: list[BpmnPoolCandidate] = Field(default_factory=list)
    lanes: list[BpmnLaneCandidate] = Field(default_factory=list)
    message_flows: list[BpmnMessageFlowCandidate] = Field(default_factory=list)
    black_box_participant_ids: list[str] = Field(default_factory=list)
    out_of_scope_participant_ids: list[str] = Field(default_factory=list)
    rationale: str | None = None


class ConsultantFinding(BaseModel):
    id: str
    finding: str
    category: Literal[
        "scope",
        "actor",
        "pool_lane",
        "activity",
        "decision",
        "handoff",
        "document",
        "exception",
        "layout",
        "assumption",
    ]
    severity: Literal["blocking", "warning", "note"] = "warning"
    recommendation: str | None = None


class ProcessDecision(BaseModel):
    id: str
    label: str
    question: str | None = None
    gateway_type: Literal["exclusive", "inclusive", "event_based"] = "exclusive"
    outcomes: list[str] = Field(default_factory=list)
    outcome_details: list[ProcessDecisionOutcome] = Field(default_factory=list)
    source_evidence: list[str] = Field(default_factory=list)


class ProcessInputOutput(BaseModel):
    step: str
    input: list[str] = Field(default_factory=list)
    output: list[str] = Field(default_factory=list)


class ProcessExceptionPath(BaseModel):
    id: str
    label: str
    trigger: str | None = None
    handling: str | None = None
    attached_to_step_id: str | None = None
    interrupting: bool = True
    is_defined: bool = True


class ProcessUnknown(BaseModel):
    question: str
    affects: str
    severity: Literal["blocking", "non_blocking", "optional_extension"] = "non_blocking"


class ProcessBoundaries(BaseModel):
    trigger: str | None = None
    start_event: str | None = None
    success_end: str | None = None
    failure_ends: list[str] = Field(default_factory=list)
    in_scope: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)


class ProcessPath(BaseModel):
    id: str
    label: str
    trigger_or_condition: str | None = None
    sequence: list[str] = Field(default_factory=list)
    rejoins_at: str | None = None
    ends_at: str | None = None
    is_confirmed: bool = True


class ProcessLoop(BaseModel):
    id: str
    label: str
    repeated_steps: list[str] = Field(default_factory=list)
    condition: str | None = None
    exit_condition: str | None = None


class ActorRelationship(BaseModel):
    actor_id: str
    organization_id: str | None = None
    relationship: Literal["internal_role", "external_participant", "system", "black_box"]
    bpmn_pool_candidate: bool = False
    bpmn_lane_candidate: bool = False


class BpmnModelingHint(BaseModel):
    element: str
    hint: str
    confidence: Literal["low", "medium", "high"] = "medium"


class ProcessConfidence(BaseModel):
    overall: Literal["low", "medium", "high"]
    weak_points: list[str] = Field(default_factory=list)


class ProcessUnderstandingDiagnostics(BaseModel):
    schema_version: str = "process_understanding_diagnostics.v1"
    source_schema_version: str
    counts: dict[str, int] = Field(default_factory=dict)
    blocking: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class QualityDimensionScore(BaseModel):
    dimension: Literal[
        "scope_boundaries",
        "actor_responsibility",
        "pool_lane_separation",
        "main_path_clarity",
        "decision_gateway_quality",
        "alternative_exception_paths",
        "document_data_rules",
        "handoffs",
        "flow_edge_readability",
        "consultant_summary_quality",
        "bpmn_compilability",
    ]
    score: int = Field(ge=1, le=10)
    findings: list[str] = Field(default_factory=list)
    blocking: bool = False


class QualityIssue(BaseModel):
    id: str
    severity: Literal["blocking", "warning", "note"]
    category: str
    message: str
    recommendation: str | None = None


class QualityImprovementAction(BaseModel):
    id: str
    priority: Literal["high", "medium", "low"] = "medium"
    target_field: str
    action: str


class ProcessUnderstandingQualityReport(BaseModel):
    schema_version: str = "process_understanding_quality.v1"
    overall_score: int = Field(ge=1, le=10)
    dimension_scores: list[QualityDimensionScore] = Field(default_factory=list)
    blocking_issues: list[QualityIssue] = Field(default_factory=list)
    warnings: list[QualityIssue] = Field(default_factory=list)
    improvement_actions: list[QualityImprovementAction] = Field(default_factory=list)
    approval_recommendation: Literal[
        "ready_to_generate",
        "needs_auto_revision",
        "needs_user_clarification",
    ]


class ProcessUnderstanding(BaseModel):
    schema_version: str = "process_understanding.v1"
    language: Literal["it", "en"] = "it"
    title: str
    objective: str | None = None
    scope: str | None = None
    actors: list[ProcessActor] = Field(default_factory=list)
    events: list[ProcessEvent] = Field(default_factory=list)
    steps: list[ProcessStep] = Field(default_factory=list)
    sequence: list[str] = Field(default_factory=list)
    decisions: list[ProcessDecision] = Field(default_factory=list)
    handoffs: list[ProcessHandoff] = Field(default_factory=list)
    data_objects: list[ProcessDataObject] = Field(default_factory=list)
    participants: list[ProcessParticipant] = Field(default_factory=list)
    bpmn_topology: BpmnParticipantTopology | None = None
    document_requirements: list[ProcessDocumentRequirement] = Field(default_factory=list)
    input_outputs: list[ProcessInputOutput] = Field(default_factory=list)
    exceptions: list[ProcessExceptionPath] = Field(default_factory=list)
    controls: list[ProcessControl] = Field(default_factory=list)
    business_rules: list[str] = Field(default_factory=list)
    structured_business_rules: list[ProcessBusinessRule] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    unknowns: list[ProcessUnknown] = Field(default_factory=list)
    narrative_focus: list[str] = Field(default_factory=list)
    boundaries: ProcessBoundaries | None = None
    main_success_path: list[str] = Field(default_factory=list)
    alternative_paths: list[ProcessPath] = Field(default_factory=list)
    out_of_scope_alternatives: list[ProcessPath] = Field(default_factory=list)
    flow_edges: list[ProcessFlowEdge] = Field(default_factory=list)
    loops: list[ProcessLoop] = Field(default_factory=list)
    actor_relationships: list[ActorRelationship] = Field(default_factory=list)
    bpmn_modeling_hints: list[BpmnModelingHint] = Field(default_factory=list)
    consultant_findings: list[ConsultantFinding] = Field(default_factory=list)
    quality_report: ProcessUnderstandingQualityReport | None = None
    confidence: ProcessConfidence | None = None


def build_process_understanding(title: str, source_text: str) -> ProcessUnderstanding:
    if settings.openai_api_key:
        try:
            process = _understanding_llm().invoke(
                [
                    SystemMessage(content=_PROCESS_UNDERSTANDING_PROMPT),
                    HumanMessage(
                        content=json.dumps(
                            {
                                "process_title": title,
                                "raw_notes": source_text,
                            },
                            ensure_ascii=False,
                        )
                    ),
                ]
            )
            return _with_quality_report(process, source_text=source_text)
        except Exception as exc:
            fallback = build_fallback_understanding(title, source_text)
            fallback.assumptions.append(f"Estrazione LLM non riuscita: {exc}")
            return _with_quality_report(fallback, source_text=source_text)

    return _with_quality_report(build_fallback_understanding(title, source_text), source_text=source_text)


def _with_quality_report(process: ProcessUnderstanding, source_text: str = "") -> ProcessUnderstanding:
    process.quality_report = evaluate_process_understanding_quality(process, source_text=source_text)
    return process


def build_fallback_understanding(title: str, source_text: str) -> ProcessUnderstanding:
    return ProcessUnderstanding(
        title=title,
        scope="ProcessUnderstanding non generato: serve esecuzione dell'extractor LLM strutturato.",
        unknowns=[
            ProcessUnknown(
                question="L'extractor LLM strutturato non ha prodotto un ProcessUnderstanding validabile.",
                affects="ProcessUnderstanding, BPMNSemanticModel e canvas BPMN",
                severity="blocking",
            )
        ],
        assumptions=[
            "Nessuna estrazione locale viene usata per inventare attori, task, gateway o documenti.",
            f"Testo sorgente disponibile ma non interpretato automaticamente ({len(source_text.strip())} caratteri).",
        ],
        confidence=ProcessConfidence(
            overall="low",
            weak_points=["Extractor LLM strutturato non disponibile o non riuscito."],
        ),
    )


def render_process_review(process: ProcessUnderstanding) -> str:
    quality = quality_report_from_understanding(process)
    lines = [
        f"## {process.title}",
        "",
        process.scope or "Review AS-IS prima della generazione BPMN.",
        "",
        f"Qualita semantica: {quality.overall_score}/10 ({quality.approval_recommendation}).",
        "",
        "Flusso principale:",
    ]

    step_by_id = {step.id: step for step in process.steps}
    sequence = process.main_success_path or process.sequence or [step.id for step in process.steps]
    for index, step_id in enumerate(sequence, start=1):
        step = step_by_id.get(step_id)
        if step:
            actor = _actor_labels(process, step.actor_ids)
            suffix = f" ({', '.join(actor)})" if actor else ""
            lines.append(f"{index}. {step.label}{suffix}")

    if process.decisions:
        lines.extend(["", "Decisioni/gateway:"])
        for decision in process.decisions:
            outcome_labels = [item.label for item in decision.outcome_details] or decision.outcomes
            outcomes = f" Esiti: {', '.join(outcome_labels)}." if outcome_labels else ""
            lines.append(f"- {decision.label}.{outcomes}".replace("..", "."))

    if process.controls:
        lines.extend(["", "Controlli e verifiche:"])
        for control in process.controls[:10]:
            owner = control.control_owner_actor_id or "owner da confermare"
            lines.append(f"- {control.label}: {control.checked_item} ({owner})")

    if process.participants:
        lines.extend(["", "Partecipanti e contenitori BPMN suggeriti:"])
        for participant in process.participants:
            detail = participant.bpmn_container
            if participant.parent_pool_id:
                detail = f"{detail} in {participant.parent_pool_id}"
            lines.append(f"- {participant.label}: {detail}")

    if process.bpmn_topology:
        lines.extend(["", "Topologia BPMN proposta:"])
        for pool in process.bpmn_topology.pools[:6]:
            intent = "black box" if pool.rendering_intent == "black_box" else pool.rendering_intent
            lines.append(f"- Pool {pool.label}: {intent}")
        for lane in process.bpmn_topology.lanes[:8]:
            lines.append(f"- Lane {lane.label}: pool {lane.pool_id}")

    if process.flow_edges:
        lines.extend(["", "Collegamenti semantici da preservare:"])
        for edge in process.flow_edges[:12]:
            condition = f" [{edge.condition}]" if edge.condition else ""
            lines.append(f"- {edge.source_id} -> {edge.target_id}: {edge.label}{condition}")

    if process.exceptions or process.alternative_paths:
        lines.extend(["", "Eccezioni e percorsi alternativi:"])
        for item in process.exceptions:
            handling = item.handling or "gestione non definita"
            lines.append(f"- {item.label}: {handling}")

    if process.data_objects:
        lines.extend(["", "Documenti/input/output rilevanti:"])
        for item in process.data_objects[:8]:
            lines.append(f"- {item.label}")

    if process.document_requirements:
        lines.extend(["", "Requisiti documentali:"])
        for item in process.document_requirements[:10]:
            required_when = f" quando {item.required_when}" if item.required_when else ""
            lines.append(f"- {item.label}{required_when}")

    if process.structured_business_rules:
        lines.extend(["", "Regole business strutturate:"])
        for rule in process.structured_business_rules[:10]:
            condition = f"Se {rule.condition}, " if rule.condition else ""
            lines.append(f"- {condition}{rule.consequence}")

    if process.consultant_findings:
        lines.extend(["", "Note consulenziali:"])
        for finding in process.consultant_findings[:8]:
            lines.append(f"- {finding.finding}")

    if quality.blocking_issues or quality.warnings:
        lines.extend(["", "Qualita e azioni correttive:"])
        for issue in [*quality.blocking_issues, *quality.warnings][:8]:
            lines.append(f"- {issue.message}")

    if process.unknowns:
        lines.extend(["", "Domande aperte:"])
        for item in process.unknowns:
            lines.append(f"- {item.question}")

    return "\n".join(lines)


def process_open_questions(process: ProcessUnderstanding) -> list[str]:
    return [item.question for item in process.unknowns if item.question.strip()]


def readiness_from_understanding(process: ProcessUnderstanding) -> int:
    return quality_report_from_understanding(process).overall_score


def quality_report_from_understanding(process: ProcessUnderstanding) -> ProcessUnderstandingQualityReport:
    return process.quality_report or conservative_process_quality_report(
        process,
        reason="Quality report assente nello stato; usato fallback conservativo.",
    )


def evaluate_process_understanding_quality(
    process: ProcessUnderstanding,
    *,
    source_text: str = "",
    bpmn_warnings: list[str] | None = None,
    use_llm: bool = True,
) -> ProcessUnderstandingQualityReport:
    if use_llm and settings.openai_api_key:
        try:
            payload = process.model_dump(mode="json")
            payload.pop("quality_report", None)
            return _quality_evaluator_llm().invoke(
                [
                    SystemMessage(content=_PROCESS_UNDERSTANDING_QUALITY_PROMPT),
                    HumanMessage(
                        content=json.dumps(
                            {
                                "source_text": source_text,
                                "process_understanding": payload,
                                "structural_diagnostics": process_understanding_diagnostics(process).model_dump(
                                    mode="json"
                                ),
                                "bpmn_validation_warnings": bpmn_warnings or [],
                            },
                            ensure_ascii=False,
                        )
                    ),
                ]
            )
        except Exception as exc:
            return conservative_process_quality_report(
                process,
                reason=f"Quality evaluator LLM non riuscito; usato fallback conservativo: {exc}",
            )

    return conservative_process_quality_report(
        process,
        reason="Quality evaluator LLM non disponibile; usato fallback conservativo.",
    )


def conservative_process_quality_report(
    process: ProcessUnderstanding,
    *,
    reason: str,
) -> ProcessUnderstandingQualityReport:
    diagnostics = process_understanding_diagnostics(process)
    warnings = [
        QualityIssue(
            id=f"QualityWarning_{index}",
            severity="warning",
            category="structural_diagnostic",
            message=message,
            recommendation="Correggere il ProcessUnderstanding o farlo rivedere dal quality evaluator.",
        )
        for index, message in enumerate(diagnostics.warnings, start=1)
    ]
    blocking_issues = [
        QualityIssue(
            id=f"QualityBlocker_{index}",
            severity="blocking",
            category="structural_diagnostic",
            message=message,
            recommendation="Correggere il riferimento strutturale prima della generazione BPMN.",
        )
        for index, message in enumerate(diagnostics.blocking, start=1)
    ]
    dimension_scores = [
        QualityDimensionScore(
            dimension="bpmn_compilability",
            score=3 if blocking_issues else 5,
            findings=[reason, *diagnostics.blocking, *diagnostics.warnings],
            blocking=bool(blocking_issues),
        )
    ]
    improvement_actions = [
        QualityImprovementAction(
            id="Improve_WithQualityEvaluator",
            priority="high",
            target_field="quality_report",
            action="Far valutare il ProcessUnderstanding dal quality evaluator LLM prima dell'approvazione.",
        )
    ]
    if not process.quality_report:
        warnings.append(
            QualityIssue(
                id="QualityWarning_FallbackEvaluator",
                severity="warning",
                category="quality_evaluator",
                message=reason,
                recommendation="Rigenerare la review quando il quality evaluator e disponibile.",
            )
        )

    return ProcessUnderstandingQualityReport(
        overall_score=3 if blocking_issues else 5,
        dimension_scores=dimension_scores,
        blocking_issues=blocking_issues,
        warnings=warnings,
        improvement_actions=improvement_actions,
        approval_recommendation="needs_user_clarification" if blocking_issues else "needs_auto_revision",
    )


def process_understanding_diagnostics(process: ProcessUnderstanding) -> ProcessUnderstandingDiagnostics:
    """
    Validate references and structural consistency in a process understanding model.
    
    Parameters:
    	process (ProcessUnderstanding): The process model to diagnose.
    
    Returns:
    	ProcessUnderstandingDiagnostics: Counts of extracted elements and lists of blocking errors and warnings.
    """
    actor_ids = {actor.id for actor in process.actors}
    step_ids = {step.id for step in process.steps}
    event_ids = {event.id for event in process.events}
    decision_ids = {decision.id for decision in process.decisions}
    known_node_ids = step_ids | event_ids | decision_ids
    path_ids = {path.id for path in [*process.alternative_paths, *process.out_of_scope_alternatives]}
    participant_ids = {participant.id for participant in process.participants}
    data_object_ids = {item.id for item in process.data_objects}
    blocking: list[str] = []
    warnings: list[str] = []

    if not process.steps:
        blocking.append("Nessuna attivita operativa estratta.")
    unknown_actor_refs = {
        actor_id
        for step in process.steps
        for actor_id in step.actor_ids
        if actor_id not in actor_ids
    }
    if unknown_actor_refs:
        blocking.append("Attivita collegate ad attori non definiti: " + ", ".join(sorted(unknown_actor_refs)))
    if any((len(decision.outcome_details) or len(decision.outcomes)) < 2 for decision in process.decisions):
        warnings.append("Alcune decisioni non hanno almeno due esiti.")
    for decision in process.decisions:
        if decision.outcomes and not decision.outcome_details:
            warnings.append(f"Decisione {decision.id} senza outcome_details strutturati.")
        for outcome in decision.outcome_details:
            has_valid_target = (
                not outcome.target_ref
                or outcome.target_ref in known_node_ids
                or outcome.target_ref in path_ids
            )
            has_valid_path = not outcome.target_path_id or outcome.target_path_id in path_ids
            if not has_valid_target or not has_valid_path:
                blocking.append(f"Esito {outcome.id} della decisione {decision.id} punta a un target non definito.")
    if process.decisions and not process.alternative_paths:
        warnings.append("Decisioni presenti senza percorsi alternativi espliciti.")
    if process.alternative_paths and not process.decisions:
        warnings.append("Percorsi alternativi presenti senza decisione/gateway sorgente.")
    for exception in process.exceptions:
        if exception.attached_to_step_id and exception.attached_to_step_id not in step_ids:
            warnings.append(
                f"Eccezione {exception.id} collegata a uno step non definito: "
                f"{exception.attached_to_step_id}."
            )
    for item in process.document_requirements:
        if item.data_object_id and item.data_object_id not in data_object_ids:
            blocking.append(f"Requisito documentale {item.id} collegato a data object non definito.")
        for actor_ref in (item.provided_by_actor_id, item.received_by_actor_id, item.validation_owner_actor_id):
            if actor_ref and actor_ref not in actor_ids:
                blocking.append(f"Requisito documentale {item.id} collegato ad attore non definito: {actor_ref}.")
    for control in process.controls:
        if control.control_owner_actor_id and control.control_owner_actor_id not in actor_ids:
            blocking.append(f"Controllo {control.id} assegnato ad attore non definito.")
        for target_ref in (control.pass_target_ref, control.fail_target_ref):
            if target_ref and target_ref not in known_node_ids and target_ref not in path_ids:
                blocking.append(f"Controllo {control.id} punta a target non definito: {target_ref}.")
    if process.bpmn_topology:
        pool_ids = {pool.id for pool in process.bpmn_topology.pools}
        for pool in process.bpmn_topology.pools:
            if pool.participant_id and pool.participant_id not in participant_ids:
                blocking.append(f"Pool candidato {pool.id} collegato a partecipante non definito.")
            unknown_pool_actor_refs = [actor_id for actor_id in pool.actor_ids if actor_id not in actor_ids]
            if unknown_pool_actor_refs:
                blocking.append(f"Pool candidato {pool.id} collegato ad attori non definiti.")
        for lane in process.bpmn_topology.lanes:
            if lane.pool_id not in pool_ids:
                blocking.append(f"Lane candidata {lane.id} collegata a pool non definito.")
            if lane.participant_id and lane.participant_id not in participant_ids:
                blocking.append(f"Lane candidata {lane.id} collegata a partecipante non definito.")
            unknown_lane_actor_refs = [actor_id for actor_id in lane.actor_ids if actor_id not in actor_ids]
            if unknown_lane_actor_refs:
                blocking.append(f"Lane candidata {lane.id} collegata ad attori non definiti.")
        for message_flow in process.bpmn_topology.message_flows:
            for participant_ref in (message_flow.from_participant_id, message_flow.to_participant_id):
                if participant_ref and participant_ref not in participant_ids:
                    blocking.append(f"Message flow {message_flow.id} collegato a partecipante non definito.")
            for actor_ref in (message_flow.from_actor_id, message_flow.to_actor_id):
                if actor_ref and actor_ref not in actor_ids:
                    blocking.append(f"Message flow {message_flow.id} collegato ad attore non definito.")
            for node_ref in (message_flow.source_ref, message_flow.target_ref):
                if node_ref and node_ref not in known_node_ids:
                    warnings.append(f"Message flow {message_flow.id} collegato a nodo non definito.")
    for edge in process.flow_edges:
        if not edge.label.strip():
            warnings.append(f"Collegamento {edge.id} senza label comprensibile.")
        if edge.source_id not in known_node_ids:
            blocking.append(f"Collegamento {edge.id} con sorgente non definita: {edge.source_id}.")
        if edge.target_id not in known_node_ids:
            blocking.append(f"Collegamento {edge.id} con destinazione non definita: {edge.target_id}.")

    return ProcessUnderstandingDiagnostics(
        source_schema_version=process.schema_version,
        counts={
            "actors": len(process.actors),
            "participants": len(process.participants),
            "steps": len(process.steps),
            "decisions": len(process.decisions),
            "flow_edges": len(process.flow_edges),
            "document_requirements": len(process.document_requirements),
            "controls": len(process.controls),
            "alternative_paths": len(process.alternative_paths),
            "out_of_scope_alternatives": len(process.out_of_scope_alternatives),
            "handoffs": len(process.handoffs),
            "topology_pools": len(process.bpmn_topology.pools) if process.bpmn_topology else 0,
            "topology_lanes": len(process.bpmn_topology.lanes) if process.bpmn_topology else 0,
            "topology_message_flows": len(process.bpmn_topology.message_flows) if process.bpmn_topology else 0,
        },
        blocking=blocking,
        warnings=warnings,
    )


@lru_cache(maxsize=1)
def _understanding_llm() -> ChatOpenAI:
    return ChatOpenAI(**chat_openai_kwargs()).with_structured_output(ProcessUnderstanding)


@lru_cache(maxsize=1)
def _quality_evaluator_llm() -> ChatOpenAI:
    return ChatOpenAI(**chat_openai_kwargs()).with_structured_output(
        ProcessUnderstandingQualityReport
    )


def _actor_labels(process: ProcessUnderstanding, actor_ids: list[str]) -> list[str]:
    by_id = {actor.id: actor.label for actor in process.actors}
    return [by_id[actor_id] for actor_id in actor_ids if actor_id in by_id]


_PROCESS_UNDERSTANDING_PROMPT = """Sei un consulente BPMN senior.

Estrai una ProcessUnderstanding strutturata dalle note grezze del processo.
Usa i fatti presenti nelle note. Quando un passaggio e necessario per rendere
coerente il processo ma non e scritto esplicitamente, inseriscilo come
assunzione o finding con certainty="inferred"; non nasconderlo nel flusso.

Regole:
- Usa italiano.
- Mantieni le attivita atomiche.
- Classifica step.type: user_task (persona con software), manual_task (attivita
  umana senza sistema), service_task (sistema/applicazione), send_task (invio
  messaggio a un altro partecipante), receive_task (attesa di un messaggio in
  ingresso), business_rule_task (valutazione di regole/decision table),
  script_task (automazione interna), subprocess (attivita scomponibile).
- Estrai attori/ruoli, partecipanti, eventi, step, decisioni/gateway, eccezioni,
  handoff, documenti, requisiti documentali, input/output, alternative path,
  loop, regole, assunzioni, findings e unknowns.
- Classifica participants.bpmn_container distinguendo pool, lane, black_box e
  out_of_scope. Non confondere persona/ente/sistema con lane.
- Popola flow_edges con source_id, target_id e label comprensibile. Ogni freccia
  deve spiegare perche si passa al nodo successivo.
- Distingui main_success_path da alternative_paths. Le alternative note ma non
  percorse non sono attivita del percorso principale; mettile in
  out_of_scope_alternatives quando sono canali o opzioni non percorse.
- Per ogni decisione inserisci question, outcomes leggibili e outcome_details
  con condizione, target_ref o target_path_id, eventuale rejoins_at o ends_process.
- Imposta gateway_type: exclusive (un solo esito, XOR), inclusive (piu' esiti
  possono valere insieme, OR) oppure event_based quando la diramazione dipende
  da quale evento arriva prima (messaggio, timer, segnale).
- Estrai controlli/verifiche in controls con owner, oggetto verificato,
  condizione di esito positivo e negativo.
- Per ogni documento importante crea data_objects e, se possibile,
  document_requirements con condizione, fornitore, ricevente e owner della verifica.
- Usa structured_business_rules per regole condizionali, specialmente requisiti,
  controlli, scadenze, eccezioni e decorrenze.
- Popola bpmn_topology con pool candidati, lane candidate e message flow
  candidati. Usa black_box o out_of_scope quando un partecipante e noto ma non
  va dettagliato nella mappa operativa.
- Lascia quality_report vuoto: sara prodotto da un evaluator separato.
- Usa id XML-safe con lettere, numeri e underscore.
- Metti in unknowns cio che manca; usa blocking solo se impedisce una bozza BPMN minima.
- Se un'eccezione e citata ma la gestione manca, usa is_defined=false.
- Per ogni eccezione collega attached_to_step_id allo step su cui puo scattare e
  imposta interrupting=false solo se lo step prosegue mentre parte la gestione.
- Distingui ruoli interni da partecipanti esterni negli actor_relationships.
- Non produrre XML e non rispondere in markdown: restituisci solo lo schema strutturato richiesto.
"""


_PROCESS_UNDERSTANDING_QUALITY_PROMPT = """Sei un quality reviewer BPMN senior, separato dall'agente che estrae il processo.

Valuta se il ProcessUnderstanding e pronto per essere mostrato all'utente come
sommario approvabile e poi trasformato in BPMN. Non riscrivere il processo:
produci solo ProcessUnderstandingQualityReport.

Criteri di giudizio:
- fedelta al testo sorgente: nessun passaggio inventato senza assumption o certainty="inferred";
- attori e responsabilita: ogni task operativo ha owner coerente;
- pool/lane/topologia: partecipanti, pool, lane, black box e out of scope sono distinti;
- percorso principale: leggibile, sinistra-destra, senza salti logici;
- gateway: decisioni con domanda, esiti, condizioni e destinazioni;
- alternative/eccezioni: canali fuori scope e casi eccezionali non confusi col main path;
- documenti, regole e controlli: requisiti, owner, condizioni e conseguenze sono espliciti;
- handoff e message flow: passaggi tra partecipanti riconoscibili;
- flow_edges: ogni freccia prevista ha una label comprensibile dal lettore;
- readiness consulenziale: il sommario deve sembrare il lavoro di un consulente Big4, non una lista generica.

Regole:
- Dai 9-10 solo se il sommario e approvabile senza ulteriore lavoro automatico.
- Se mancano pool/lane, owner dei task, gateway o flow_edges leggibili, non usare ready_to_generate.
- Usa blocking_issues quando la generazione BPMN sarebbe fuorviante o strutturalmente illegale.
- Usa warnings per problemi migliorabili automaticamente.
- Ogni improvement_action deve indicare quale campo strutturato correggere.
- Non premiare la sola presenza di campi: valuta la coerenza semantica con il testo sorgente.
- Restituisci solo lo schema strutturato richiesto, senza markdown.
"""
