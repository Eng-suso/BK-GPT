from operator import add
from typing import Annotated

from backend.graphs.common import ConversationState
from backend.bpmn import BPMNSemanticModel
from backend.process_understanding import (
    ProcessUnderstanding,
    ProcessUnderstandingDiagnostics,
    ProcessUnderstandingQualityReport,
)


class CanvasState(ConversationState):
    scope_type: str
    scope_key: str
    project_id: str
    process_id: str
    bpmn_model_id: str
    process_name: str | None
    current_bpmn_xml: str | None
    process_understanding: ProcessUnderstanding | None
    process_understanding_diagnostics: ProcessUnderstandingDiagnostics | None
    process_quality_report: ProcessUnderstandingQualityReport | None
    bpmn_semantic_model: BPMNSemanticModel | None
    readiness_score: int | None
    missing_information: list[str]
    # Lacune del piano con le alternative proposte e cio' che e' gia' stato deciso.
    review_open_questions: list[dict]
    saved_bpmn_xml: str | None
    effective_bpmn_xml: str | None
    effective_bpmn_xml_source: str | None

    # Lo stato del processo su cui questo run sta lavorando, cosi' come il
    # Process Agent lo possiede. Il Canvas non lo ricostruisce: lo riceve, lo
    # cita e, se cambia mentre sta lavorando, se ne accorge.
    process_snapshot: dict | None
    process_snapshot_id: str | None
    process_snapshot_label: str | None
    # La versione su cui il run e' partito. Alla fine si confronta con quella
    # corrente: se e' cambiata, il disegno appena prodotto descrive uno stato
    # che non e' piu' quello ufficiale.
    canvas_run_snapshot_id: str | None
    # done | waiting_for_user | failed. Il Canvas e' un runtime agentico, e un
    # runtime agentico dichiara come e' finito.
    #
    # Il quarto esito - annullato - non vive qui perche' il grafo non puo'
    # osservarlo: l'annullamento e' del turno, e appartiene al runtime dello
    # stream, che quando il client si stacca esce dal generatore del grafo e
    # ferma le passate in corso. Scriverlo qui significherebbe dichiarare uno
    # stato che nessuno imposta. Cio' che rende sicuro l'annullamento non e'
    # l'etichetta: e' che nessuna scrittura viene dichiarata senza rilettura,
    # quindi un run interrotto a meta' non lascia dietro un canvas che al giro
    # dopo si legge come riuscito.
    canvas_run_status: str | None
    canvas_pending_question: dict | None

    canvas_route: str | None
    # La route con cui il run e' partito. `canvas_route` viene riscritta dal loop
    # di correzione; questa no, e i controlli che dipendono da come il run e' nato
    # leggono questa.
    canvas_initial_route: str | None
    canvas_mode: str | None
    canvas_objective: str | None
    canvas_expected_outcome: str | None
    # full_from_plan | partial_change | from_user_description. Decide se la
    # costruzione passa dal comando deterministico o da un subagente.
    canvas_construction_kind: str | None
    # Le durate di fase dell'ultima generazione deterministica, per capire dove
    # e' stato speso il tempo senza dover leggere i log.
    canvas_draft_metrics: dict | None
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
    delegation_target: str | None
    delegation_reason: str | None
    delegation_payload: dict
    routing_confidence: float
    needs_clarification: bool
    clarification_question: str | None
    entity_hints: dict

    validation_report: dict | None
    construction_plan: dict | None
    # XML dell'anteprima appena generata: l'apply la rilegge da qui invece di
    # farsela rispedire dal modello.
    canvas_preview_xml: str | None
    preview_diff: dict | None
    canvas_layout_plan: dict | None
    canvas_layout_report: dict | None
    canvas_layout_status: str | None
    canvas_warnings: list[str]
    canvas_next_actions: list[dict]
    canvas_loop_status: str | None
    canvas_loop_attempt: int
    canvas_loop_max_attempts: int
    canvas_initial_saved_bpmn_xml: str | None
    canvas_last_validation: dict | None
    canvas_task_log: Annotated[list[dict], add]
    routing_trace: Annotated[list[dict], add]
    delegation_events: Annotated[list[dict], add]
