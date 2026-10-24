"""La review del BPMN: domande e risposte, versioni, preparazione, revisione e
approvazione.
"""

import json
import logging

from sqlalchemy import select

from backend.agents.chat_mode import assert_write_allowed
from backend.process_understanding import (
    ProcessUnderstanding,
    ProcessUnknown,
    quality_report_from_understanding,
    unknown_question_id,
)
from backend.workspace_database._common import decode_list, encode_list, now_iso, slugify, tenant_id, tenant_row
from backend.workspace_database.bpmn import (
    NO_PRECONDITION,
    _assert_bpmn_not_changed_underneath,
    _remember_turn_write,
    create_bpmn_version,
)
from backend.workspace_database.conformance import _queue_conformance, conformance_state, decode_element_decisions
from backend.workspace_services.bpmn_canvas_edit import optimize_bpmn_layout
from backend.workspace_services.bpmn_review import build_bpmn_review_draft, bpmn_xml_from_review
from backend.workspace_storage import (
    WorkspaceBpmnModel,
    WorkspaceBpmnReview,
    WorkspaceBpmnReviewVersion,
    workspace_connection,
)


logger = logging.getLogger("backend.workspace_database")


def _open_missing_information(review) -> list[str]:
    """Filter unresolved review information to exclude questions already answered.
    
    Args:
        review (object): Untrusted review record containing stored missing-information
            and answer data.
    
    Returns:
        list[str]: Missing-information items whose question identifiers have not been
        answered.
    
    The function does not modify or persist the review.
    """
    answered = {
        unknown_question_id(item.get("question") or "")
        for item in decode_answers(review)
    }
    return [
        item
        for item in decode_list(review.missing_information_json)
        if unknown_question_id(item) not in answered
    ]


def decode_answers(review) -> list[dict]:
    """Decode a review's stored answers into a list.
    
    Args:
        review: An object whose ``answers_json`` attribute contains JSON data.
            The stored value is treated as untrusted input.
    
    Returns:
        The decoded list of answer dictionaries, or an empty list when the
        attribute is missing, empty, or contains a JSON value of another type.
    
    Raises:
        json.JSONDecodeError: If ``answers_json`` contains malformed JSON.
    """
    parsed = json.loads(getattr(review, "answers_json", "[]") or "[]")
    return parsed if isinstance(parsed, list) else []


def answered_unknowns(review) -> list[ProcessUnknown]:
    """Le domande a cui il consulente ha risposto, da riportare nel piano nuovo.

    La domanda si prende dal piano corrente quando c'e' - con il suo contesto,
    le alternative, la gravita' - e altrimenti si ricostruisce dal testo salvato
    insieme alla risposta: una risposta data a una versione di tre ricostruzioni
    fa resta comunque la risposta di chi conosce il processo (L9).

    Args:
        review: La review corrente, o ``None`` per un piano che nasce adesso.

    Returns:
        Le domande risposte, nell'ordine in cui sono state risposte.

    Sola lettura.
    """
    if review is None:
        return []
    answers = decode_answers(review)
    if not answers:
        return []
    semantic_model = json.loads(getattr(review, "bpmn_semantic_model_json", None) or "{}")
    understanding = semantic_model.get("sourceProcessUnderstanding") or {}
    current = {
        unknown_question_id(str(item.get("question") or "")): item
        for item in understanding.get("unknowns") or []
        if isinstance(item, dict) and item.get("question")
    }
    carried: list[ProcessUnknown] = []
    for answer in answers:
        question = " ".join(str(answer.get("question") or "").split())
        question_id = str(answer.get("question_id") or unknown_question_id(question))
        raw = current.get(question_id) or ({"question": question, "affects": ""} if question else None)
        if raw is None:
            continue
        try:
            carried.append(ProcessUnknown.model_validate(raw))
        except ValueError:
            logger.warning("domanda risposta non riportabile nel piano: %s", question_id, exc_info=True)
    return carried


def unanswered_questions(review) -> list[dict]:
    """Identify review questions that still require an answer.
    
    Args:
        review: Untrusted review data from which to derive open questions.
    
    Returns:
        A list of question dictionaries whose answers are empty or absent.
    """
    return [item for item in open_questions_with_answers(review) if not item.get("answer")]


def open_questions_with_answers(review) -> list[dict]:
    """
    Builds actionable review questions from the stored process understanding and recorded answers.
    
    Args:
        review: [Untrusted] Review record containing the serialized semantic model and answers.
    
    Returns:
        A list of question dictionaries with stable IDs, alternatives, severity,
        impact, and any recorded answer metadata.
    
    Raises:
        json.JSONDecodeError: If the stored semantic model is not valid JSON.
    
    This function does not modify or persist data.
    """
    semantic_model = json.loads(review.bpmn_semantic_model_json or "{}")
    understanding = semantic_model.get("sourceProcessUnderstanding") or {}
    answers = {item.get("question_id"): item for item in decode_answers(review)}

    questions = []
    for unknown in understanding.get("unknowns") or []:
        if not isinstance(unknown, dict):
            continue
        question = str(unknown.get("question") or "").strip()
        if not question:
            continue
        question_id = unknown_question_id(question)
        questions.append(
            {
                "question_id": question_id,
                "question": question,
                "affects": unknown.get("affects") or "",
                "severity": unknown.get("severity") or "non_blocking",
                # Da dove nasce la domanda: quale voce ha detto cosa, e cosa
                # resta scoperto. Senza questo al consulente arriva "chi
                # approva?" - una domanda da questionario, indistinguibile da
                # quella che si farebbe prima di aver sentito qualcuno.
                "grounded_in": str(unknown.get("grounded_in") or ""),
                "options": [
                    {
                        "label": str(option.get("label") or ""),
                        "implication": str(option.get("implication") or ""),
                    }
                    for option in unknown.get("options") or []
                    if isinstance(option, dict) and option.get("label")
                ],
                "answer": answers.get(question_id, {}).get("answer"),
                "answered_at": answers.get(question_id, {}).get("answered_at"),
            }
        )
    return questions


def answer_bpmn_review_question(
    bpmn_model_id: str,
    question: str,
    answer: str,
) -> dict:
    """Record or replace an answer to a BPMN review question and persist a review-version snapshot.
    
    Args:
        bpmn_model_id (str): Untrusted BPMN model identifier.
        question (str): Untrusted question text; must contain non-whitespace content.
        answer (str): Untrusted answer text; must contain non-whitespace content.
    
    Returns:
        dict: The updated BPMN review, including the recorded answer and incremented version.
    
    Raises:
        ValueError: If the question or answer is empty, or if no tenant-owned review
            exists for the specified BPMN model.
    
    The answer is stored for later review revision and does not modify the process model.
    """
    assert_write_allowed("answer_bpmn_review_question")
    clean_question = " ".join(str(question or "").split())
    clean_answer = str(answer or "").strip()
    if not clean_question:
        raise ValueError("Domanda obbligatoria.")
    if not clean_answer:
        raise ValueError("La risposta non può essere vuota.")

    with workspace_connection() as session:
        review = tenant_row(session, WorkspaceBpmnReview, bpmn_model_id)
        if review is None:
            raise ValueError("Nessuna review BPMN da aggiornare per questo canvas.")

        question_id = unknown_question_id(clean_question)
        recorded = [
            item
            for item in decode_answers(review)
            if item.get("question_id") != question_id
        ]
        recorded.append(
            {
                "question_id": question_id,
                "question": clean_question,
                "answer": clean_answer,
                "answered_at": now_iso(),
            }
        )

        review.version = int(getattr(review, "version", 1) or 1) + 1
        review.answers_json = json.dumps(recorded, ensure_ascii=False)
        review.updated_at = now_iso()
        _record_review_version(
            session,
            review,
            change_summary=f"Risposta a: {clean_question}",
            source="answer",
        )
        session.flush()
        return review_to_dict(review)


class UnreadableReviewError(ValueError):
    """La review salvata non e' leggibile, e riprovare non la rendera' tale.

    Un semantic model legacy o un ProcessUnderstanding placeholder da estrazione
    fallita restano quello che sono finche' qualcuno non rigenera il piano:
    nessun tentativo successivo cambia l'esito. Il tipo serve a chi lavora una
    coda, che altrimenti non puo' distinguere questo da una chiamata al modello
    andata storta - e rimette in coda per sempre una riga che fallira' sempre.
    """


def _review_artifacts(review) -> tuple[dict, dict]:
    """Validate and derive artifacts from a stored BPMN review.

    Args:
        review: Untrusted stored review row containing serialized semantic-model data.

    Returns:
        A tuple containing the canonical semantic model and its recomputed quality
        report.

    Raises:
        UnreadableReviewError: If the stored semantic model is not canonical, or if
            the stored process understanding cannot be validated or has no
            applicable quality report (extraction-failure placeholder). Sempre
            permanente: la review va rigenerata, non riletta.
        json.JSONDecodeError: If the stored payload cannot be decoded.

    The function does not persist changes or otherwise modify the review.
    """
    bpmn_semantic_model = json.loads(review.bpmn_semantic_model_json or "{}")
    if not _is_canonical_semantic_model_payload(bpmn_semantic_model):
        raise UnreadableReviewError("Review BPMN legacy rifiutata: semantic model non canonicale.")
    process_understanding = bpmn_semantic_model.get("sourceProcessUnderstanding") or {}
    try:
        quality_report = quality_report_from_understanding(
            ProcessUnderstanding.model_validate(process_understanding)
        ).model_dump(mode="json")
    except ValueError as exc:
        # `ValidationError` di pydantic e' un `ValueError`: struttura non valida e
        # placeholder da estrazione fallita finiscono nello stesso stato, ed e'
        # lo stesso stato - questa review non si puo' leggere cosi' com'e'.
        raise UnreadableReviewError(
            f"Review BPMN non leggibile per {getattr(review, 'bpmn_model_id', '?')}: {exc}"
        ) from exc
    return bpmn_semantic_model, quality_report


def review_version_to_dict(version: WorkspaceBpmnReviewVersion) -> dict:
    """
    Serialize a BPMN review version with its semantic model, quality report, questions, answers, and metadata.
    
    Args:
        version (WorkspaceBpmnReviewVersion): Review version to serialize.
    
    Returns:
        dict: Serialized review version data, including open questions and decoded answers.
    
    Raises:
        ValueError: If the stored review artifacts are invalid.
    
    The function does not modify or persist the review version.
    """
    bpmn_semantic_model, quality_report = _review_artifacts(version)
    return {
        "bpmn_model_id": version.bpmn_model_id,
        "process_id": version.process_id,
        "version": version.version,
        "status": version.status,
        "change_summary": version.change_summary,
        "source": version.source,
        "source_text": version.source_text,
        "process_understanding": bpmn_semantic_model.get("sourceProcessUnderstanding") or {},
        "bpmn_semantic_model": bpmn_semantic_model,
        "quality_report": quality_report,
        "bpmn_brief": version.bpmn_brief,
        "readiness_score": version.readiness_score,
        "missing_information": _open_missing_information(version),
        # La provenance viaggia anche nella storia: "questa versione del piano su
        # quali fonti era costruita" e' la domanda che rende leggibile un
        # confronto fra due versioni, e la colonna la salvava gia' senza che
        # nessuno potesse rileggerla.
        "evidence_source_set_id": getattr(version, "evidence_source_set_id", None),
        "open_questions": open_questions_with_answers(version),
        "answers": decode_answers(version),
        "created_at": version.created_at,
    }


def _record_review_version(
    session,
    review: WorkspaceBpmnReview,
    *,
    change_summary: str,
    source: str,
) -> WorkspaceBpmnReviewVersion:
    """Create a persistent snapshot of the review at its current version.
    
    Args:
        change_summary (str): Untrusted description of the change represented by
            the snapshot.
        source (str): Untrusted identifier for the snapshot's origin.
    
    Returns:
        WorkspaceBpmnReviewVersion: The newly created, unsaved snapshot object.
    
    Side effects:
        Adds the snapshot to the provided database session.
    """
    version = WorkspaceBpmnReviewVersion(
        tenant_id=getattr(review, "tenant_id", tenant_id()),
        bpmn_model_id=review.bpmn_model_id,
        process_id=review.process_id,
        version=review.version,
        source_text=review.source_text,
        process_understanding_json=review.process_understanding_json,
        bpmn_semantic_model_json=review.bpmn_semantic_model_json,
        bpmn_brief=review.bpmn_brief,
        readiness_score=review.readiness_score,
        missing_information_json=review.missing_information_json,
        evidence_source_set_id=getattr(review, "evidence_source_set_id", None),
        answers_json=getattr(review, "answers_json", "[]") or "[]",
        status=review.status,
        change_summary=change_summary,
        source=source,
        created_at=now_iso(),
    )
    session.add(version)
    return version


def _mark_review_version_approved(session, review: WorkspaceBpmnReview) -> None:
    """Mark the current review version as approved in the review history.
    
    If no matching historical snapshot exists, records one before marking approval.
    Persists the approval status and summary through the supplied database session.
    
    Args:
        session: Database session used to update or create the review version.
        review: Review whose tenant, BPMN model, and version identify the snapshot.
    
    """
    row = (
        session.execute(
            select(WorkspaceBpmnReviewVersion).where(
                WorkspaceBpmnReviewVersion.bpmn_model_id == review.bpmn_model_id,
                WorkspaceBpmnReviewVersion.version == review.version,
                WorkspaceBpmnReviewVersion.tenant_id == getattr(review, "tenant_id", tenant_id()),
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        # A review stored before versioning existed has no snapshot to mark; record
        # one now so its approval is not the only state missing from the history.
        _record_review_version(
            session,
            review,
            change_summary="Piano approvato: canvas generato",
            source="approval",
        )
        return

    row.status = "approved"
    row.change_summary = "Piano approvato: canvas generato"


def list_bpmn_review_versions(bpmn_model_id: str) -> list[dict]:
    """List tenant-scoped review snapshots for a BPMN model, newest first.
    
    Args:
        bpmn_model_id (str): Untrusted BPMN model identifier used to select review
            snapshots within the current tenant.
    
    Returns:
        list[dict]: Review snapshots ordered from newest to oldest. Returns an
            empty list when no snapshots match.
    """
    with workspace_connection() as session:
        rows = (
            session.execute(
                select(WorkspaceBpmnReviewVersion)
                .where(
                    WorkspaceBpmnReviewVersion.bpmn_model_id == bpmn_model_id,
                    WorkspaceBpmnReviewVersion.tenant_id == tenant_id(),
                )
                .order_by(WorkspaceBpmnReviewVersion.version.desc())
            )
            .scalars()
            .all()
        )
        return [review_version_to_dict(row) for row in rows]


def get_bpmn_review_version(bpmn_model_id: str, version: int) -> dict | None:
    """Retrieve a tenant-scoped BPMN review version.
    
    Args:
        bpmn_model_id: Untrusted BPMN model identifier.
        version: Untrusted review version number.
    
    Returns:
        A serialized review version for the current tenant, or `None` if no matching
        version exists.
    """
    with workspace_connection() as session:
        row = (
            session.execute(
                select(WorkspaceBpmnReviewVersion).where(
                    WorkspaceBpmnReviewVersion.bpmn_model_id == bpmn_model_id,
                    WorkspaceBpmnReviewVersion.version == version,
                    WorkspaceBpmnReviewVersion.tenant_id == tenant_id(),
                )
            )
            .scalars()
            .first()
        )
        return review_version_to_dict(row) if row else None


def review_to_dict(review: WorkspaceBpmnReview) -> dict:
    """Serialize a BPMN review and its derived artifacts for API responses.
    
    Args:
        review (WorkspaceBpmnReview): Review record to serialize.
    
    Returns:
        dict: Review data including semantic model, quality report, readiness,
            missing information, questions, answers, status, and timestamps.
    
    This function does not modify or persist the review.
    """
    bpmn_semantic_model, quality_report = _review_artifacts(review)
    process_understanding = bpmn_semantic_model.get("sourceProcessUnderstanding") or {}
    return {
        "bpmn_model_id": review.bpmn_model_id,
        "process_id": review.process_id,
        "version": getattr(review, "version", 1),
        "source_text": review.source_text,
        "process_understanding": process_understanding,
        "bpmn_semantic_model": bpmn_semantic_model,
        "quality_report": quality_report,
        "bpmn_brief": review.bpmn_brief,
        "readiness_score": review.readiness_score,
        "missing_information": _open_missing_information(review),
        # Su quali fonti questo piano e' nato. Chi legge puo' confrontarlo con il
        # registro dell'evidenza di adesso e sapere se il piano e' indietro.
        "evidence_source_set_id": getattr(review, "evidence_source_set_id", None),
        "open_questions": open_questions_with_answers(review),
        "answers": decode_answers(review),
        "element_decisions": decode_element_decisions(review),
        "conformance": conformance_state(review),
        "status": getattr(review, "status", "pending"),
        "created_at": review.created_at,
        "updated_at": review.updated_at,
    }


def get_bpmn_review(bpmn_model_id: str, include_approved: bool = False) -> dict | None:
    with workspace_connection() as session:
        review = tenant_row(session, WorkspaceBpmnReview, bpmn_model_id)

        if review is None:
            return None
        if not include_approved and getattr(review, "status", "pending") != "pending":
            return None
        stored_semantic_model = json.loads(review.bpmn_semantic_model_json or "{}")
        if not _is_canonical_semantic_model_payload(stored_semantic_model):
            return None

        return review_to_dict(review)


def update_bpmn_review_brief(bpmn_model_id: str, bpmn_brief: str) -> dict:
    """Update the reader-facing narrative of a pending BPMN review.
    
    Args:
        bpmn_model_id (str): Untrusted BPMN model identifier used to locate the
            tenant-owned review.
        bpmn_brief (str): Untrusted Markdown brief. It is trimmed and must contain
            non-whitespace content.
    
    Returns:
        dict: The updated serialized BPMN review.
    
    Raises:
        ValueError: If the brief is empty, or if no pending tenant-owned review
            exists for the specified model.
    
    Side Effects:
        Persists the trimmed brief, increments the review version, updates its
        timestamp, and records a new review-version snapshot. The semantic model
        and canvas-generation content remain unchanged.
    """
    assert_write_allowed("update_bpmn_review_brief")
    clean_brief = bpmn_brief.strip()
    if not clean_brief:
        raise ValueError("Il piano Markdown non può essere vuoto.")

    with workspace_connection() as session:
        review = tenant_row(session, WorkspaceBpmnReview, bpmn_model_id)
        if review is None or getattr(review, "status", "pending") != "pending":
            raise ValueError("Nessuna review BPMN pendente da salvare.")

        review.version = int(getattr(review, "version", 1) or 1) + 1
        review.bpmn_brief = clean_brief
        review.updated_at = now_iso()
        _record_review_version(
            session,
            review,
            change_summary="Testo del piano modificato",
            source="brief_edit",
        )
        session.flush()
        return review_to_dict(review)


def _is_canonical_semantic_model_payload(value: dict) -> bool:
    return bool(
        value.get("flowNodes")
        and value.get("sequenceFlows")
        and value.get("compilationPlan")
        and value.get("sourceProcessUnderstanding")
    )


# "Non e' stato detto" e "e' stato detto: nessuna fonte" sono due cose diverse, e
# `None` non poteva esprimerle entrambe. I chiamanti che non conoscono il set di
# fonti - i tool che ricostruiscono la review da prosa - passavano implicitamente
# `None` e cancellavano la provenance di un piano nato dalle interviste: da quel
# momento il piano risultava "di provenienza ignota" e veniva risintetizzato a
# ogni giro.
class _KeepExistingValue:
    """L'argomento non e' stato passato, che non e' "passato vuoto"."""

    __slots__ = ()


_KEEP_EVIDENCE_SOURCE_SET = _KeepExistingValue()


def prepare_bpmn_review(
    bpmn_model_id: str,
    process_description: str,
    process_understanding: dict | None = None,
    evidence_source_set_id: str | None | _KeepExistingValue = _KEEP_EVIDENCE_SOURCE_SET,
) -> dict:
    """Prepare and persist a pending BPMN review for a model.
    
    Args:
        bpmn_model_id (str): Untrusted BPMN model identifier. The model must belong to
            the current tenant.
        process_description (str): Untrusted process description. It must contain
            non-whitespace text.
        process_understanding (dict | None): Untrusted optional process understanding
            used to generate the review draft.
        evidence_source_set_id (str | None): Identity of the evidence source set this
            plan was built on. Recorded so a later turn can tell an up-to-date plan
            from one that predates a source. Omit it to keep whatever the existing
            review declares: a caller that does not know the source set must not
            erase the provenance of a plan that was built on the interviews.

    Returns:
        dict: The serialized, pending BPMN review.
    
    Raises:
        ValueError: If the process description is empty or the BPMN model cannot be
            found for the current tenant.
    
    The review is persisted in the workspace. A new review starts at version 1;
    preparing an existing review creates its next version while preserving the
    previous snapshot.
    """
    assert_write_allowed("prepare_bpmn_review")
    clean_text = process_description.strip()
    if not clean_text:
        raise ValueError("Descrizione processo obbligatoria.")

    with workspace_connection() as session:
        current_tenant_id = tenant_id()
        model = tenant_row(session, WorkspaceBpmnModel, bpmn_model_id)

        if model is None:
            raise ValueError(f"Modello BPMN non trovato: {bpmn_model_id}")

        review = session.get(WorkspaceBpmnReview, bpmn_model_id)
        if review is not None and getattr(review, "tenant_id", "local") != current_tenant_id:
            review = None

        bpmn_process_id = f"Process_{slugify(model.process.name, 'process').replace('-', '_')}"
        review_draft = build_bpmn_review_draft(
            bpmn_process_id=bpmn_process_id,
            process_name=model.process.name,
            source_text=clean_text,
            process_understanding=process_understanding,
            # Una ricostruzione del piano riparte dalle fonti, ma le risposte del
            # consulente non vengono dalle fonti: si riportano, non si
            # rigenerano (L9). E' qui e non in chi chiama perche' questo e'
            # l'unico punto da cui passa ogni ricostruzione, presente e futura.
            answered_questions=answered_unknowns(review),
        )

        timestamp = now_iso()

        if review is None:
            review = WorkspaceBpmnReview(
                tenant_id=current_tenant_id,
                bpmn_model_id=bpmn_model_id,
                process_id=model.process_id,
                version=1,
                source_text=review_draft.source_text,
                process_understanding_json=review_draft.process_understanding_json(),
                bpmn_semantic_model_json=review_draft.bpmn_semantic_model_json(),
                bpmn_brief=review_draft.bpmn_brief,
                readiness_score=review_draft.readiness_score,
                missing_information_json=encode_list(review_draft.missing_information),
                evidence_source_set_id=(
                    None
                    if isinstance(evidence_source_set_id, _KeepExistingValue)
                    else evidence_source_set_id
                ),
                status="pending",
                created_at=timestamp,
                updated_at=timestamp,
            )
            session.add(review)
        else:
            # A new preparation does not erase the previous plan: it becomes the
            # next version, and what it replaced stays readable and comparable.
            review.version = int(getattr(review, "version", 1) or 1) + 1
            review.source_text = review_draft.source_text
            review.process_understanding_json = review_draft.process_understanding_json()
            review.bpmn_semantic_model_json = review_draft.bpmn_semantic_model_json()
            review.bpmn_brief = review_draft.bpmn_brief
            review.readiness_score = review_draft.readiness_score
            review.missing_information_json = encode_list(review_draft.missing_information)
            if not isinstance(evidence_source_set_id, _KeepExistingValue):
                review.evidence_source_set_id = evidence_source_set_id
            review.status = "pending"
            review.updated_at = timestamp

        # Il piano e' cambiato: il confronto con le fonti che risultava prima
        # descrive un altro piano. Va rifatto, e lo fa il worker.
        _queue_conformance(review)
        _record_review_version(
            session,
            review,
            change_summary="Piano preparato dalla descrizione del processo",
            source="prepare",
        )
        session.flush()
        return review_to_dict(review)


def revise_bpmn_review(
    bpmn_model_id: str,
    process_understanding: dict,
    change_summary: str = "",
) -> dict:
    """Rebuild a pending BPMN review from corrected process understanding.
    
    Args:
        bpmn_model_id (str): Untrusted BPMN model identifier scoped to the current tenant.
        process_understanding (dict): Untrusted corrected process understanding used to
            regenerate the review artifacts.
        change_summary (str): Untrusted description recorded with the revision snapshot.
    
    Raises:
        ValueError: If the BPMN model is not found for the current tenant or no review
            exists for the model.
    
    Returns:
        dict: The revised review, including its regenerated brief, semantic model,
            readiness data, missing information, status, and version.
    
    The revision persists the updated review, records a historical version, increments
    the review version, and reopens the review with pending status.
    """
    assert_write_allowed("revise_bpmn_review")
    with workspace_connection() as session:
        model = tenant_row(session, WorkspaceBpmnModel, bpmn_model_id)
        if model is None:
            raise ValueError(f"Modello BPMN non trovato: {bpmn_model_id}")

        review = tenant_row(session, WorkspaceBpmnReview, bpmn_model_id)
        if review is None:
            raise ValueError("Nessuna review BPMN da rivedere per questo canvas.")

        bpmn_process_id = f"Process_{slugify(model.process.name, 'process').replace('-', '_')}"
        review_draft = build_bpmn_review_draft(
            bpmn_process_id=bpmn_process_id,
            process_name=model.process.name,
            source_text=review.source_text,
            process_understanding=process_understanding,
            answered_questions=answered_unknowns(review),
        )

        review.version = int(getattr(review, "version", 1) or 1) + 1
        review.process_understanding_json = review_draft.process_understanding_json()
        review.bpmn_semantic_model_json = review_draft.bpmn_semantic_model_json()
        review.bpmn_brief = review_draft.bpmn_brief
        review.readiness_score = review_draft.readiness_score
        review.missing_information_json = encode_list(review_draft.missing_information)
        # A revision reopens the plan: an approved review that gets corrected is a
        # new proposal, not a still-approved one.
        review.status = "pending"
        # E il confronto con le fonti descriveva il piano di prima: va rifatto.
        _queue_conformance(review)
        review.updated_at = now_iso()

        _record_review_version(
            session,
            review,
            change_summary=change_summary.strip() or "Piano rivisto dal consulente",
            source="revision",
        )
        session.flush()
        return review_to_dict(review)


def approve_bpmn_review(bpmn_model_id: str, *, override: bool = False) -> dict:
    """
    Approve a BPMN review and persist the generated BPMN model.
    
    Args:
        bpmn_model_id (str): Untrusted identifier of the tenant-scoped BPMN model.
        override (bool): Whether to bypass review-readiness checks.
    
    Returns:
        dict: A payload containing the approved BPMN model and review data.
    
    Raises:
        ValueError: If the BPMN model or review does not exist, or the review is
            not ready for approval.
        PermissionError: If the caller is not authorized to perform writes.
    
    The function persists the generated BPMN XML, records a BPMN version linked to
    the approved review version, and marks the review as approved.
    """
    assert_write_allowed("approve_bpmn_review")
    with workspace_connection() as session:
        model = tenant_row(session, WorkspaceBpmnModel, bpmn_model_id)
        review = tenant_row(session, WorkspaceBpmnReview, bpmn_model_id)

        if model is None:
            raise ValueError(f"Modello BPMN non trovato: {bpmn_model_id}")
        if review is None:
            raise ValueError("Nessuna review BPMN pronta da approvare per questo canvas.")

        if not override:
            _assert_review_ready_for_approval(review)

        # L'approvazione scrive il disegno come ogni altra strada: in fila dietro
        # le scritture concorrenti, mai sopra una versione che il turno non ha
        # visto, e registrata come scrittura del turno.
        session.refresh(model, with_for_update=True)
        _assert_bpmn_not_changed_underneath(session, model.id, NO_PRECONDITION)
        xml, _layout_report = optimize_bpmn_layout(bpmn_xml_from_review(
            bpmn_semantic_model_json=review.bpmn_semantic_model_json,
        ))
        model.xml = xml
        approved_version = int(getattr(review, "version", 1) or 1)
        approved_drawing = create_bpmn_version(
            session=session,
            model=model,
            xml=xml,
            # Which plan produced this drawing, so a canvas version can be traced
            # back to the review it came from.
            change_summary=f"Generazione da review BPMN approvata (v{approved_version})",
            source="review_approval",
        )
        review.status = "approved"
        review.updated_at = now_iso()
        # Il disegno generato e' nuovo: il confronto con le fonti va rifatto.
        _queue_conformance(review)
        # Approving does not change what the plan says, only its standing, so the
        # recorded version is marked rather than duplicated.
        _mark_review_version_approved(session, review)
        review_payload = review_to_dict(review)
        session.flush()
        _remember_turn_write(model.id, approved_drawing.id)
        return {
            "bpmn_model": {
                "id": model.id,
                "process_id": model.process_id,
                "name": model.name,
                "xml": model.xml,
            },
            "review": review_payload,
        }


# Il valutatore chiede all'utente di chiarire; una volta che l'utente ha
# chiarito, l'attesa non ha piu' oggetto. Le altre raccomandazioni riguardano il
# modello, non l'utente, e continuano a bloccare.
_RECOMMENDATION_WAITING_ON_THE_USER = "needs_user_clarification"


def review_approval_blockers(
    quality_report: dict | None,
    semantic_model: dict | None,
    *,
    open_questions_pending: bool = True,
) -> list[str]:
    """Identifies reasons a BPMN review cannot be automatically approved.
    
    Args:
        quality_report (dict | None): Untrusted quality-evaluation data. A
            recommendation other than ``"ready_to_generate"`` is a blocker, except
            ``"needs_user_clarification"`` when ``open_questions_pending`` is
            ``False``.
        semantic_model (dict | None): Untrusted semantic-model data checked for
            control-flow soundness.
        open_questions_pending (bool): Whether unanswered review questions remain.
    
    Returns:
        list[str]: Approval-blocker descriptions. Invalid semantic-model data
        contributes no control-flow blockers.
    
    The function performs no persistence or other side effects.
    """
    from backend.bpmn import BPMNSemanticModel
    from backend.bpmn.soundness import analyze_control_flow

    blockers: list[str] = []
    recommendation = (quality_report or {}).get("approval_recommendation")
    waiting_on_answered_questions = (
        recommendation == _RECOMMENDATION_WAITING_ON_THE_USER and not open_questions_pending
    )
    if recommendation and recommendation != "ready_to_generate" and not waiting_on_answered_questions:
        blockers.append(f"la valutazione qualita' e' '{recommendation}', non 'ready_to_generate'.")

    try:
        model = BPMNSemanticModel.model_validate(semantic_model or {})
    except Exception:
        return blockers
    for issue in analyze_control_flow(model).errors:
        blockers.append(f"control-flow: {issue.message}")
    return blockers


def _assert_review_ready_for_approval(review: WorkspaceBpmnReview) -> None:
    """Validate that a BPMN review satisfies all approval requirements.
    
    Args:
        review (WorkspaceBpmnReview): Review to validate.
    
    Raises:
        ValueError: If the review has one or more approval blockers.
    
    The function does not modify or persist the review.
    """
    payload = review_to_dict(review)
    blockers = review_approval_blockers(
        payload.get("quality_report"),
        payload.get("bpmn_semantic_model"),
        open_questions_pending=bool(unanswered_questions(review)),
    )
    if blockers:
        raise ValueError(
            "Review non approvabile: "
            + "; ".join(blockers[:5])
            + ". Correggere il processo oppure approvare con override."
        )
