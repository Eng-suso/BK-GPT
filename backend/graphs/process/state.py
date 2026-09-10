from operator import add
from typing import Annotated

from backend.graphs.common import ConversationState
from backend.bpmn import BPMNSemanticModel
from backend.process_understanding import (
    ProcessUnderstanding,
    ProcessUnderstandingDiagnostics,
    ProcessUnderstandingQualityReport,
)


class ProcessState(ConversationState):
    scope_type: str
    scope_key: str
    project_id: str
    process_id: str
    process_name: str | None
    bpmn_model_id: str | None
    process_understanding: ProcessUnderstanding | None
    process_understanding_diagnostics: ProcessUnderstandingDiagnostics | None
    process_quality_report: ProcessUnderstandingQualityReport | None
    bpmn_semantic_model: BPMNSemanticModel | None
    readiness_score: int | None
    draft_readiness: dict | None
    validation_readiness: dict | None
    missing_information: list[str]
    # Lacune del piano con le alternative proposte e cio' che e' gia' stato deciso.
    review_open_questions: list[dict]
    saved_bpmn_xml: str | None

    process_route: str | None
    process_mode: str | None
    process_objective: str | None
    process_phase: str | None
    goal: str | None
    intent: str | None
    next_action: str | None
    suggested_capability: str | None
    authorized_capability: str | None
    orchestration_status: str | None
    termination_reason: str | None
    blocking_conditions: list[str]
    required_context: list[str]
    reasoning_summary: str | None
    workflow_scope: str | None
    engineering_loop_iteration: int
    engineering_loop_max_iterations: int
    minimum_readiness_score: int | None
    process_no_progress_count: int
    process_progress_signature: str | None
    process_continue_loop: bool
    # Quale artefatto questo turno modifica - il piano di modellazione o il
    # disegno - e in quale modalita' il runtime lo sta facendo. Erano due
    # informazioni che nessuno portava: senza la prima le due operazioni erano
    # indistinguibili, senza la seconda la modalita' la si deduceva dalla chat.
    target_artifact: str | None
    active_chat_mode: str | None
    required_chat_mode: str | None
    # Il loop di review del piano: il giudizio dell'ultima rilettura, quante
    # correzioni sono gia' state tentate e se ne vale un'altra.
    plan_review: dict | None
    plan_review_attempt: int
    plan_review_continue: bool
    plan_review_issues: list[str]
    delegation_target: str | None
    delegation_reason: str | None
    delegation_payload: dict
    routing_confidence: float
    needs_clarification: bool
    clarification_question: str | None
    entity_hints: dict

    discovery_readiness: dict | None
    evidence_coverage: dict | None
    canvas_handoff_payload: dict | None
    # Il registro dell'evidenza persistita di questo processo, ricaricato a ogni
    # apertura di turno da `load_process_context`. Non e' un accumulatore: e' lo
    # stato del knowledge graph, quindi si sostituisce, non si somma.
    evidence_ledger: dict | None

    routing_trace: Annotated[list[dict], add]
    delegation_events: Annotated[list[dict], add]
    process_claims: Annotated[list[dict], add]
    process_gaps: Annotated[list[dict], add]
    contradictions: Annotated[list[dict], add]
    # Cio' che ogni specialista ha concluso nella sua passata. Non e' un
    # messaggio: e' materiale per la risposta unica che il consulente legge a
    # fine giro. Un turno con tre passate produceva tre sintesi consegnate una
    # dietro l'altra, ognuna quasi identica alla precedente.
    specialist_findings: Annotated[list[dict], add]
