from typing import Annotated

from langchain_core.tools import InjectedToolCallId, tool
from langgraph.types import Command
from pydantic import BaseModel, Field

from backend import workspace_database
from backend.agents.evidence_brief import (
    render_ledger_lines,
    render_source_evidence,
    turn_evidence_ledger,
)
from backend.agents.process_plan import (
    plan_readiness,
    review_process_plan,
    write_process_plan,
)
from backend.agents.process_snapshot import (
    PLAN_IGNORES_EVIDENCE_REMEDY,
    build_process_snapshot,
    plan_ignores_evidence,
)
from backend.bpmn import build_bpmn_semantic_model, validate_bpmn_semantic_model
from backend.graphs.process.nodes import evidence_count, load_evidence_ledger
from backend.graphs.process.tools import (
    bpmn_semantic_model_from_payload,
    prepare_canvas_handoff,
    process_understanding_from_payload,
    process_workspace_payload,
)
from backend.process_understanding import (
    ProcessUnderstanding,
    draft_readiness_from_understanding,
    evaluate_process_understanding_quality,
    process_understanding_diagnostics,
    render_process_review,
    validation_readiness_from_understanding,
)
from backend.toolsets.workspace import enterprise_state_write, enterprise_tool_result
from backend.workspace_services.write_verification import verify_review_persisted


class ProcessUnderstandingReviewInput(BaseModel):
    process_id: str = Field(description="Current process id.")
    process_description: str = Field(
        description=(
            "Evidence-backed process description. Include confirmed flow, actors, decisions, "
            "handoffs, exceptions, data, assumptions and explicit gaps."
        )
    )
    process_understanding: ProcessUnderstanding | None = Field(
        default=None,
        description=(
            "Preferred canonical ProcessUnderstanding. Use when the LLM has enough evidence to "
            "structure actors, participants, pool/lane candidates, document requirements, rules, "
            "decisions, paths and labeled semantic edges directly."
        ),
    )
    evidence_summary: str = Field(default="", description="Sources and claims that support the description.")
    known_assumptions: list[str] = Field(default_factory=list, description="Assumptions to preserve in the review.")
    unresolved_gaps: list[str] = Field(default_factory=list, description="Open gaps to preserve as unknowns.")


class UnderstandingReadinessInput(BaseModel):
    process_id: str = Field(description="Current process id.")
    objective: str = Field(description="Why readiness is being checked.")
    minimum_readiness_score: int = Field(default=7, ge=1, le=10, description="Minimum score before canvas handoff.")


class ProcessPlanAmendmentInput(BaseModel):
    process_id: str = Field(description="Current process id.")
    process_understanding: ProcessUnderstanding = Field(
        description=(
            "What this amendment adds to or corrects in the plan. It may be partial: "
            "what you do not restate is kept, not deleted. Structure everything the "
            "evidence supports - participants with pool/lane/black-box classification, "
            "lane candidates, activities with their owner, main path, alternative and "
            "urgent paths, decisions, exception paths, document requirements, business "
            "rules, and the gaps that stay open as unknowns."
        )
    )
    change_summary: str = Field(
        default="",
        description="What changed and why, recorded with the new plan version.",
    )
    rebuild_from_scratch: bool = Field(
        default=False,
        description=(
            "False (default) merges into the current plan. True discards the current "
            "plan and replaces it with this one - only when the consultant explicitly "
            "asked to redo the plan from scratch."
        ),
    )


class QualityEvaluationInput(BaseModel):
    process_id: str = Field(description="Current process id.")
    objective: str = Field(
        description="Why the Modeling subagent is evaluating ProcessUnderstanding quality."
    )


@tool(args_schema=UnderstandingReadinessInput)
def validate_process_understanding_readiness(
    process_id: str,
    objective: str,
    minimum_readiness_score: int = 7,
    *,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> Command:
    """
    Validate whether the current ProcessUnderstanding is ready for BPMN semantic
    modeling or canvas handoff. Use before deriving BPMN or delegating to Canvas.

    """
    payload = process_workspace_payload(process_id)
    review = payload["review"]
    understanding = process_understanding_from_payload(payload)
    warnings = []

    if review is None or understanding is None:
        # Senza piano ci sono due stati, non uno: un processo con evidenza agli
        # atti e' sintetizzabile - il materiale c'e', manca il passo che lo
        # struttura - mentre un processo senza fonti va prima raccontato.
        # Collassarli in "not_modelable" e' il difetto che faceva rispondere
        # "non posso modellarlo" a un processo con tre interviste.
        from backend.agents.process_snapshot import (
            draft_readiness_without_plan,
            validation_readiness_without_plan,
        )

        process = payload["process"]
        evidence_snapshot = load_evidence_ledger(
            (process or {}).get("project_id"), process_id
        )
        recorded = evidence_count(evidence_snapshot)
        draft_readiness = draft_readiness_without_plan(recorded)
        missing = draft_readiness["reason"]
        warnings.append(missing)
        score = 0
        validation_readiness = validation_readiness_without_plan()
    else:
        score = int(review.get("readiness_score") or 0)
        draft_readiness = draft_readiness_from_understanding(understanding)
        validation_readiness = validation_readiness_from_understanding(understanding)
        warnings.extend(draft_readiness["blockers"])

    # Il gate del canvas chiede una bozza disegnabile, non una bozza validata:
    # le lacune aperte viaggiano dentro il modello preliminare invece di
    # impedirlo. Cio' che manca per l'approvazione resta in validation_readiness.
    status = (
        "ready_for_modeling"
        if draft_readiness["status"] in {"modelable", "synthesizable"}
        else "review_required"
    )
    return enterprise_state_write(
        tool_call_id=tool_call_id,
        # The bar this process has to clear before canvas handoff. The agent sets
        # it here; `minimum_readiness_score()` reads it back at the gate.
        state={
            "minimum_readiness_score": minimum_readiness_score,
            "draft_readiness": draft_readiness,
            "validation_readiness": validation_readiness,
        },
        status=status,
        action="validate_process_understanding_readiness",
        entity_type="process_understanding_readiness",
        entity_id=process_id,
        summary=objective,
        payload={
            "process_id": process_id,
            "minimum_readiness_score": minimum_readiness_score,
            "readiness_score": score,
            "draft_readiness": draft_readiness,
            "validation_readiness": validation_readiness,
            "missing_information": review.get("missing_information") if review else [],
        },
        warnings=warnings,
    )


@tool(args_schema=ProcessUnderstandingReviewInput)
def prepare_process_understanding_review(
    process_id: str,
    process_description: str,
    process_understanding: ProcessUnderstanding | None = None,
    evidence_summary: str = "",
    known_assumptions: list[str] | None = None,
    unresolved_gaps: list[str] | None = None,
) -> str:
    """
    Build and save a pending ProcessUnderstanding/BPMNSemanticModel review for
    one process. Use only after discovery/evidence synthesis, not from generic
    free text. This does not approve or save final BPMN XML.

    The runtime counts the process claims already on record. A review that
    carries no actors, participants or activities while claims exist is refused:
    the evidence has not reached the plan, and saving it would make that gap the
    official state of the process.
    """
    process = workspace_database.get_process(process_id)
    if process is None:
        raise ValueError(f"Processo non trovato: {process_id}")

    evidence_snapshot = load_evidence_ledger(process.get("project_id"), process_id)
    ignored_evidence = plan_ignores_evidence(
        process_understanding, evidence_count(evidence_snapshot)
    )
    if ignored_evidence:
        raise ValueError(f"{ignored_evidence} {PLAN_IGNORES_EVIDENCE_REMEDY}")

    projected_claims = turn_evidence_ledger({"evidence_ledger": evidence_snapshot})
    sections = [
        "Authoritative process evidence:\n" + render_source_evidence(evidence_snapshot),
        "Projected claims with provenance:\n" + render_ledger_lines(projected_claims),
        process_description.strip(),
    ]
    if evidence_summary.strip():
        sections.append("Evidence summary:\n" + evidence_summary.strip())
    if known_assumptions:
        sections.append("Known assumptions:\n" + "\n".join(f"- {item}" for item in known_assumptions))
    if unresolved_gaps:
        sections.append("Unresolved gaps:\n" + "\n".join(f"- {item}" for item in unresolved_gaps))

    previous = workspace_database.get_bpmn_review(
        process["bpmn_model_id"], include_approved=True
    )
    previous_version = int((previous or {}).get("version") or 0)

    workspace_database.prepare_bpmn_review(
        bpmn_model_id=process["bpmn_model_id"],
        process_description="\n\n".join(sections),
        process_understanding=process_understanding.model_dump(mode="json") if process_understanding else None,
        # Il piano dichiara su quali fonti e' nato: al turno dopo si puo' sapere
        # se e' ancora aggiornato o se descrive un processo di un'intervista fa.
        evidence_source_set_id=str(evidence_snapshot.get("source_set_id") or ""),
    )
    # Write -> persistence -> read-after-write. Cio' che si riporta al consulente
    # e' cio' che il database ha accettato, non cio' che si e' chiesto di
    # scrivere: e' la differenza fra "review aggiornata" e una review a zero
    # attori che continua a mostrarsi com'era.
    #
    # La versione attesa fa parte della verifica: una rilettura che torna alla
    # versione di prima e' il modo silenzioso in cui una scrittura sparisce, e
    # rileggere solo il contenuto la lasciava passare - il piano vecchio ha
    # attori, quindi la review "conteneva un piano" e il turno si chiudeva bene.
    review = verify_review_persisted(
        process["bpmn_model_id"],
        expect_plan_content=True,
        minimum_version=previous_version + 1,
    )
    # La review salvata e' la sola versione che conta da qui in poi: le due
    # soglie si ricavano da quella, non dal ProcessUnderstanding proposto, cosi'
    # il consulente legge nel payload la stessa readiness che il gate del canvas
    # ricalcolera' al turno dopo.
    saved_understanding = ProcessUnderstanding.model_validate(review["process_understanding"])
    diagnostics = process_understanding_diagnostics(saved_understanding)
    return enterprise_tool_result(
        status="prepared",
        action="prepare_process_understanding_review",
        entity_type="process_understanding_review",
        entity_id=process_id,
        summary=f"ProcessUnderstanding review prepared for {process['name']}.",
        payload={
            "process_id": process_id,
            "bpmn_model_id": process["bpmn_model_id"],
            "readiness_score": review["readiness_score"],
            "draft_readiness": draft_readiness_from_understanding(saved_understanding),
            "validation_readiness": validation_readiness_from_understanding(saved_understanding),
            "evidence_source_set_id": evidence_snapshot.get("source_set_id"),
            "evidence_source_ids": evidence_snapshot.get("source_ids") or [],
            "missing_information": review["missing_information"],
            "process_review_markdown": review["bpmn_brief"],
            "process_understanding": review["process_understanding"],
            "process_understanding_diagnostics": diagnostics.model_dump(mode="json"),
            "quality_report": review["quality_report"],
            "bpmn_semantic_model": review["bpmn_semantic_model"],
        },
        warnings=review["missing_information"] + diagnostics.warnings + diagnostics.blocking,
    )


@tool(args_schema=ProcessPlanAmendmentInput)
def amend_process_plan(
    process_id: str,
    process_understanding: ProcessUnderstanding,
    change_summary: str = "",
    rebuild_from_scratch: bool = False,
) -> str:
    """
    Add to, correct or extend the MODELING PLAN of this process, and save it as a
    new version. This is the tool for "mettilo nel piano", "aggiungi al piano",
    "aggiorna il piano" and "crea il piano con quello che sai".

    The plan is a separate artifact from the BPMN canvas. This changes the plan
    and does NOT touch the diagram: nothing is drawn, no canvas mode is needed,
    and applying the plan to the canvas is a different request.

    The amendment may be partial. What you do not restate is preserved: the plan
    is merged, not replaced, so a request that adds an urgent path does not erase
    the three lanes the plan already knew. Real gaps stay gaps - record them as
    unknowns instead of dropping the activities around them.

    A plan is a draft by construction: single-source or not-yet-validated
    knowledge belongs in it, carrying its provenance and its uncertainty. Draft
    readiness and validation readiness are two different thresholds and this tool
    reports both.

    The write is verified by reading the plan back. If the reread version does not
    carry the change, this reports a failure - it never reports a save it cannot
    confirm.
    """
    result = write_process_plan(
        process_id,
        process_understanding,
        strategy="replace" if rebuild_from_scratch else "amend",
        change_summary=change_summary,
    )
    if result.action in {"process_not_found", "rejected_empty_plan", "write_failed"}:
        raise ValueError(result.reason)

    snapshot = result.snapshot
    plan_review = review_process_plan(snapshot)
    readiness = plan_readiness(snapshot)
    return enterprise_tool_result(
        status="saved" if result.persisted else "unchanged",
        action="amend_process_plan",
        entity_type="process_modeling_plan",
        entity_id=process_id,
        summary=(
            f"Piano {snapshot.label if snapshot else ''} salvato "
            f"({result.diff.as_sentence()})."
            if result.persisted
            else result.reason
        ),
        payload={
            "process_id": process_id,
            "bpmn_model_id": snapshot.bpmn_model_id if snapshot else None,
            "plan_version": result.version,
            "previous_plan_version": result.previous_version,
            "plan_snapshot_id": snapshot.snapshot_id if snapshot else None,
            "plan_snapshot_label": snapshot.label if snapshot else None,
            "persisted": result.persisted,
            "changes": result.diff.as_dict(),
            **readiness,
            "process_review_markdown": (result.review or {}).get("bpmn_brief"),
            "missing_information": (result.review or {}).get("missing_information") or [],
            "open_questions": (result.review or {}).get("open_questions") or [],
        },
        warnings=[*plan_review.issues, *plan_review.warnings],
        next_actions=(
            [{"owner": "process_modeling_agent", "action": "fix_plan_issues"}]
            if plan_review.issues
            else []
        ),
    )


@tool
def read_process_plan(process_id: str) -> str:
    """
    Read the modeling plan of this process as it is persisted: its version, its
    structure, the human-readable review, the gaps still open, and the two
    readiness thresholds. Use before amending it, so an amendment adds to what is
    there instead of restating it, and before asking the consultant to approve,
    correct or continue to the canvas.

    A process with no plan yet is not an error: it reports `no_plan`, which is a
    different state from a plan that exists and is thin.
    """
    snapshot = build_process_snapshot(process_id)
    if snapshot is None:
        raise ValueError(f"Processo non trovato: {process_id}")

    plan_review = review_process_plan(snapshot)
    understanding = (
        ProcessUnderstanding.model_validate(snapshot.process_understanding)
        if snapshot.process_understanding
        else None
    )
    return enterprise_tool_result(
        status="ok" if snapshot.has_semantic_model else "no_plan",
        action="read_process_plan",
        entity_type="process_modeling_plan",
        entity_id=process_id,
        summary=(
            f"Piano {snapshot.label} di {snapshot.process_name}: "
            f"{len([q for q in snapshot.open_questions if not q.answer])} lacune aperte."
        ),
        payload={
            "process_id": process_id,
            "plan_version": snapshot.version,
            "plan_snapshot_id": snapshot.snapshot_id,
            "plan_snapshot_label": snapshot.label,
            "process_understanding": snapshot.process_understanding,
            # La resa leggibile sta qui e non in un tool suo: chiederla era un
            # secondo giro sullo stesso artefatto, e il toolset si tiene piccolo
            # per non far scegliere al modello fra due letture della stessa cosa.
            "review_markdown": render_process_review(understanding) if understanding else "",
            "process_understanding_diagnostics": (
                process_understanding_diagnostics(understanding).model_dump(mode="json")
                if understanding
                else None
            ),
            "open_questions": [item.model_dump(mode="json") for item in snapshot.open_questions],
            "missing_information": snapshot.missing_information,
            **plan_readiness(snapshot),
        },
        warnings=[*plan_review.issues, *plan_review.warnings],
    )


@tool(args_schema=QualityEvaluationInput)
def evaluate_prepared_process_understanding_quality(process_id: str, objective: str) -> str:
    """
    Ask the ProcessUnderstanding quality evaluator to review the prepared
    semantic summary before approval or canvas handoff.
    """
    payload = process_workspace_payload(process_id)
    review = payload["review"]
    process = payload["process"]
    understanding = process_understanding_from_payload(payload)
    model = bpmn_semantic_model_from_payload(payload)
    if review is None or understanding is None:
        raise ValueError("ProcessUnderstanding review non disponibile per questo processo.")

    semantic_warnings = validate_bpmn_semantic_model(model) if model else []
    quality_report = evaluate_process_understanding_quality(
        understanding,
        source_text=str(review.get("source_text") or ""),
        bpmn_warnings=semantic_warnings,
    )
    return enterprise_tool_result(
        status="ready" if quality_report.approval_recommendation == "ready_to_generate" else "review_required",
        action="evaluate_prepared_process_understanding_quality",
        entity_type="process_understanding_quality",
        entity_id=process_id,
        summary=objective,
        payload={
            "process_id": process_id,
            "bpmn_model_id": process["bpmn_model_id"],
            "quality_report": quality_report.model_dump(mode="json"),
            "semantic_warnings": semantic_warnings,
        },
        warnings=[
            issue.message
            for issue in [*quality_report.blocking_issues, *quality_report.warnings]
        ],
    )


@tool
def derive_bpmn_semantic_model(process_id: str) -> str:
    """
    Derive a BPMNSemanticModel from the current ProcessUnderstanding and return
    validation warnings. Use after a ProcessUnderstanding review exists.
    """
    payload = process_workspace_payload(process_id)
    process = payload["process"]
    understanding = process_understanding_from_payload(payload)
    if understanding is None:
        raise ValueError("ProcessUnderstanding non disponibile per questo processo.")

    model = build_bpmn_semantic_model(
        process_id=f"Process_{process['id'].replace('-', '_')}",
        process_name=process["name"],
        process=understanding,
    )
    warnings = validate_bpmn_semantic_model(model)
    return enterprise_tool_result(
        status="prepared" if not warnings else "review_required",
        action="derive_bpmn_semantic_model",
        entity_type="bpmn_semantic_model",
        entity_id=process_id,
        summary=f"BPMNSemanticModel derived for {process['name']}.",
        payload={
            "process_id": process_id,
            "bpmn_model_id": process["bpmn_model_id"],
            "bpmn_semantic_model": model.model_dump(mode="json"),
            "validation_warnings": warnings,
        },
        warnings=warnings,
    )


@tool
def validate_prepared_bpmn_semantic_model(process_id: str) -> str:
    """
    Validate the BPMNSemanticModel stored in the current pending process review.
    Use before Canvas Macro handoff.
    """
    payload = process_workspace_payload(process_id)
    process = payload["process"]
    model = bpmn_semantic_model_from_payload(payload)
    if model is None:
        raise ValueError("BPMNSemanticModel non disponibile per questo processo.")

    warnings = validate_bpmn_semantic_model(model)
    return enterprise_tool_result(
        status="valid" if not warnings else "review_required",
        action="validate_prepared_bpmn_semantic_model",
        entity_type="bpmn_semantic_model_validation",
        entity_id=process_id,
        summary=f"BPMNSemanticModel validation for {process['name']}.",
        payload={
            "process_id": process_id,
            "bpmn_model_id": process["bpmn_model_id"],
            "node_count": len(model.flowNodes),
            "flow_count": len(model.sequenceFlows),
            "lane_count": len(model.lanes),
            "model_warnings": model.model_warnings,
            "validation_warnings": warnings,
        },
        warnings=warnings,
    )


# `render_process_understanding_review` viveva qui: leggeva lo stesso artefatto di
# `read_process_plan` e ne rendeva la sola parte leggibile, senza la versione ne'
# le due soglie. Due letture della stessa cosa costringono il modello a scegliere
# fra loro, e la scelta sbagliata era quella che non diceva su quale versione
# stava lavorando. La resa markdown e' dentro `read_process_plan`.


MODELING_TOOL_POLICY = """
Process Modeling subagent tools.

The Modeling subagent owns ONE artifact: the modeling plan (ProcessUnderstanding
and the BPMNSemanticModel derived from it). The BPMN diagram is a different
artifact with a different owner. Changing the plan draws nothing, and it does not
need a canvas mode.

Two operations on the plan, and they are not the same:

- amend_process_plan - add to, correct or extend the plan. This is the default,
  and it is what "mettilo nel piano", "aggiungi al piano", "aggiorna il piano"
  and "crea il piano con quello che sai" ask for. The amendment may be partial:
  what you do not restate is kept. Read the current plan first
  (read_process_plan) so you add instead of repeating - it also gives you the
  version you are working on and the human-readable review to show.
- prepare_process_understanding_review - rebuild the plan from the evidence
  narrative. Use it for a first full AS-IS mapping or when the consultant asked
  to redo the plan from scratch. It replaces what is there.

The structure carries the meaning, not the prose. Whatever the evidence supports
must reach the plan as structure: participants with pool/lane/black-box
classification, lane candidates, every activity with its owner, the main path,
alternative and urgent paths, decisions with their outcomes, exception paths,
document requirements, business rules and labeled flow_edges. A rich narrative
saved as a paragraph is knowledge lost: the next reader gets bullets.

Two thresholds, and they are separate. Draft readiness authorises a plan with its
gaps declared inside it; validation readiness authorises calling the AS-IS
validated. Single-source or not-yet-corroborated knowledge belongs in the draft,
carrying its provenance - do not drop an activity because only one voice
described it. A real gap stays a gap: record it as an unknown next to the
activities you do know, never by deleting them.

After a plan write, use evaluate_prepared_process_understanding_quality. If the
runtime reports plan issues, fix those and amend again before canvas handoff.
""".strip()


modeling_tools = [
    read_process_plan,
    amend_process_plan,
    validate_process_understanding_readiness,
    prepare_process_understanding_review,
    evaluate_prepared_process_understanding_quality,
    derive_bpmn_semantic_model,
    validate_prepared_bpmn_semantic_model,
    prepare_canvas_handoff,
]
