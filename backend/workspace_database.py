import json
import re
from datetime import UTC, datetime

from sqlalchemy import func, select

from backend.agents.chat_mode import assert_write_allowed
from backend.process_understanding import (
    ProcessUnderstanding,
    quality_report_from_understanding,
    unknown_question_id,
)
from backend.security import get_current_tenant_id
from backend.workspace_defaults import (
    UNKNOWN_NEXT_STEP,
    UNKNOWN_OWNER,
    UNKNOWN_SECTOR,
    is_unknown_client_status,
    normalize_client_status,
    resolve_client_status,
    resolve_project_phase,
    resolve_project_status,
)
from backend.workspace_services.bpmn_review import build_bpmn_review_draft, bpmn_xml_from_review
from backend.workspace_services.bpmn_canvas_edit import optimize_bpmn_layout
from backend.workspace_storage import (
    WorkspaceBpmnModel,
    WorkspaceBpmnReview,
    WorkspaceBpmnReviewVersion,
    WorkspaceBpmnVersion,
    WorkspaceClient,
    WorkspaceDecision,
    WorkspaceProcess,
    WorkspaceProject,
    WorkspaceSimulationRun,
    WorkspaceSource,
    workspace_connection,
)


def encode_list(values: list[str]) -> str:
    return json.dumps(values, ensure_ascii=False)


def decode_list(value: str) -> list[str]:
    parsed = json.loads(value or "[]")
    return parsed if isinstance(parsed, list) else []


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def tenant_id() -> str:
    return get_current_tenant_id()


def tenant_row(session, model, row_id: str):
    row = session.get(model, row_id)
    if row is None or getattr(row, "tenant_id", "local") != tenant_id():
        return None
    return row


def slugify(value: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or fallback


def normalize_name(value: str) -> str:
    return " ".join(value.casefold().split())


def unique_id(session, model, base_id: str) -> str:
    candidate = base_id
    suffix = 2

    while session.get(model, candidate) is not None:
        candidate = f"{base_id}-{suffix}"
        suffix += 1

    return candidate


def process_to_dict(process: WorkspaceProcess) -> dict:
    return {
        "id": process.id,
        "project_id": process.project_id,
        "bpmn_model_id": process.bpmn_model_id,
        "name": process.name,
        "stage": process.stage,
        "status": process.status,
        "owner": process.owner,
        "readiness": process.readiness,
    }


def project_to_dict(project: WorkspaceProject, include_processes: bool = True) -> dict:
    return {
        "id": project.id,
        "client_id": project.client_id,
        "client": project.client.name,
        "name": project.name,
        "objective": project.objective or "",
        "phase": project.phase,
        "status": project.status,
        "progress": project.progress,
        "processes": project.process_count,
        "next_step": project.next_step,
        "milestones": decode_list(project.milestones_json),
        "open_issues": decode_list(project.open_issues_json),
        "deliverables": decode_list(project.deliverables_json),
        "process_items": [process_to_dict(process) for process in project.processes]
        if include_processes
        else [],
    }


def client_to_dict(client: WorkspaceClient) -> dict:
    projects = list(client.projects)
    processes = [process.name for project in projects for process in project.processes]
    documents = [
        deliverable
        for project in projects
        for deliverable in decode_list(project.deliverables_json)
    ]
    next_activity = projects[0].next_step if projects else "Nessuna attivita aperta"

    return {
        "id": client.id,
        "name": client.name,
        "sector": client.sector,
        "status": client.status,
        "projects": len(projects),
        "next_activity": next_activity,
        "owner": client.owner,
        "contact": client.contact,
        "processes": processes,
        "documents": documents,
    }


def list_clients() -> list[dict]:
    with workspace_connection() as session:
        clients = session.execute(
            select(WorkspaceClient)
            .where(WorkspaceClient.tenant_id == tenant_id())
            .order_by(WorkspaceClient.name)
        ).scalars().all()
        return [client_to_dict(client) for client in clients]


def fill_client_placeholders(
    client: WorkspaceClient,
    *,
    sector: str | None,
    status: str | None,
    owner: str | None,
    contact: str | None,
) -> None:
    """Riempie i soli campi rimasti al placeholder, senza toccare i dati curati.

    `create_client` e' idempotente per nome: chiamarla due volte non crea un
    duplicato. Ma "non creo un duplicato" non deve voler dire "butto via quello
    che l'utente ha appena detto": se il record esiste con `status` ancora al
    placeholder e ora l'utente dichiara un cliente acquisito, quel campo si
    riempie. Un valore gia' deciso non viene mai sovrascritto da una create
    successiva - cambiarlo e' un update, e questa non lo e'.
    """
    if sector and client.sector in ("", UNKNOWN_SECTOR):
        client.sector = sector
    if status and is_unknown_client_status(client.status):
        client.status = status
    if owner and client.owner in ("", UNKNOWN_OWNER):
        client.owner = owner
    if contact and not client.contact:
        client.contact = contact


def create_client(
    name: str,
    sector: str | None = None,
    status: str | None = None,
    owner: str | None = None,
    contact: str | None = None,
) -> dict:
    """Crea il cliente, o restituisce quello esistente arricchito coi campi noti.

    Ogni campo diverso dal nome e' opzionale davvero: `None` significa "non
    dichiarato" e diventa placeholder qui, in un punto solo. Nessun chiamante
    deve piu' inventare un default - era cosi' che un cliente appena acquisito
    finiva registrato come "Prospect".
    """
    clean_name = name.strip()

    if not clean_name:
        raise ValueError("Il nome cliente è obbligatorio.")

    stated_sector = (sector or "").strip() or None
    stated_status = normalize_client_status(status)
    stated_owner = (owner or "").strip() or None
    stated_contact = (contact or "").strip() or None

    with workspace_connection() as session:
        current_tenant_id = tenant_id()
        existing_clients = session.execute(
            select(WorkspaceClient).where(WorkspaceClient.tenant_id == current_tenant_id)
        ).scalars().all()
        existing_client = next(
            (
                client
                for client in existing_clients
                if normalize_name(client.name) == normalize_name(clean_name)
            ),
            None,
        )

        if existing_client is not None:
            fill_client_placeholders(
                existing_client,
                sector=stated_sector,
                status=stated_status,
                owner=stated_owner,
                contact=stated_contact,
            )
            session.flush()
            return client_to_dict(existing_client)

        client_id = unique_id(session, WorkspaceClient, slugify(clean_name, "client"))
        client = WorkspaceClient(
            id=client_id,
            tenant_id=current_tenant_id,
            name=clean_name,
            sector=stated_sector or UNKNOWN_SECTOR,
            status=resolve_client_status(stated_status),
            owner=stated_owner or UNKNOWN_OWNER,
            contact=stated_contact or "",
        )
        session.add(client)
        session.flush()
        return client_to_dict(client)


def list_projects() -> list[dict]:
    with workspace_connection() as session:
        projects = session.execute(
            select(WorkspaceProject)
            .where(WorkspaceProject.tenant_id == tenant_id())
            .order_by(WorkspaceProject.name)
        ).scalars().all()
        return [project_to_dict(project) for project in projects]


def create_project(
    client_id: str,
    name: str,
    objective: str | None = None,
    phase: str | None = None,
    status: str | None = None,
    progress: int = 0,
    next_step: str | None = None,
    milestones: list[str] | None = None,
    open_issues: list[str] | None = None,
    deliverables: list[str] | None = None,
) -> dict:
    """Crea il progetto. Ogni campo oltre a cliente e nome e' opzionale davvero.

    `None` significa "non dichiarato" e diventa placeholder qui, in un punto
    solo: fase e stato non hanno piu' un default nella firma di ogni chiamante.
    `objective` e' il perche' dell'incarico e non ha placeholder - una frase
    inventata al posto del consulente sarebbe peggio di un campo vuoto.
    """
    clean_name = name.strip()

    if not clean_name:
        raise ValueError("Il nome progetto è obbligatorio.")

    with workspace_connection() as session:
        current_tenant_id = tenant_id()
        client = tenant_row(session, WorkspaceClient, client_id)

        if client is None:
            raise ValueError(f"Cliente non trovato: {client_id}")

        project_id = unique_id(session, WorkspaceProject, slugify(clean_name, "project"))
        project = WorkspaceProject(
            id=project_id,
            tenant_id=current_tenant_id,
            client_id=client_id,
            name=clean_name,
            objective=(objective or "").strip(),
            phase=resolve_project_phase(phase),
            status=resolve_project_status(status),
            progress=max(0, min(int(progress), 100)),
            process_count=0,
            next_step=(next_step or "").strip() or UNKNOWN_NEXT_STEP,
            milestones_json=encode_list(milestones or []),
            open_issues_json=encode_list(open_issues or []),
            deliverables_json=encode_list(deliverables or []),
        )
        session.add(project)
        session.flush()
        return project_to_dict(project)


def update_client(
    client_id: str,
    name: str | None = None,
    sector: str | None = None,
    status: str | None = None,
    owner: str | None = None,
    contact: str | None = None,
) -> dict:
    """Aggiorna i campi dichiarati di un cliente. `None` = "non toccare".

    Diverso da `create_client`, che riempie solo i placeholder: qui il chiamante
    (il consulente dalla UI, o l'agente su sua richiesta) sta correggendo un
    valore gia' deciso, e la correzione deve passare.
    """
    with workspace_connection() as session:
        client = tenant_row(session, WorkspaceClient, client_id)

        if client is None:
            raise ValueError(f"Cliente non trovato: {client_id}")

        if name is not None:
            clean_name = name.strip()
            if not clean_name:
                raise ValueError("Il nome cliente è obbligatorio.")
            client.name = clean_name
        if sector is not None:
            client.sector = sector.strip() or UNKNOWN_SECTOR
        if status is not None:
            client.status = resolve_client_status(status)
        if owner is not None:
            client.owner = owner.strip() or UNKNOWN_OWNER
        if contact is not None:
            client.contact = contact.strip()

        session.flush()
        return client_to_dict(client)


def update_project(
    project_id: str,
    name: str | None = None,
    client_id: str | None = None,
    objective: str | None = None,
    phase: str | None = None,
    status: str | None = None,
    progress: int | None = None,
    next_step: str | None = None,
    milestones: list[str] | None = None,
    open_issues: list[str] | None = None,
    deliverables: list[str] | None = None,
) -> dict:
    """Aggiorna i campi dichiarati di un progetto. `None` = "non toccare".

    Le liste arrivano intere: chi le manda ha appena visto quelle correnti nella
    UI, quindi una lista vuota e' "svuotala", non "non dichiarata".
    """
    with workspace_connection() as session:
        project = tenant_row(session, WorkspaceProject, project_id)

        if project is None:
            raise ValueError(f"Progetto non trovato: {project_id}")

        if name is not None:
            clean_name = name.strip()
            if not clean_name:
                raise ValueError("Il nome progetto è obbligatorio.")
            project.name = clean_name
        if client_id is not None and client_id != project.client_id:
            client = tenant_row(session, WorkspaceClient, client_id)
            if client is None:
                raise ValueError(f"Cliente non trovato: {client_id}")
            project.client_id = client_id
        if objective is not None:
            project.objective = objective.strip()
        if phase is not None:
            project.phase = resolve_project_phase(phase)
        if status is not None:
            project.status = resolve_project_status(status)
        if progress is not None:
            project.progress = max(0, min(int(progress), 100))
        if next_step is not None:
            project.next_step = next_step.strip() or UNKNOWN_NEXT_STEP
        if milestones is not None:
            project.milestones_json = encode_list(_clean_list(milestones))
        if open_issues is not None:
            project.open_issues_json = encode_list(_clean_list(open_issues))
        if deliverables is not None:
            project.deliverables_json = encode_list(_clean_list(deliverables))

        session.flush()
        return project_to_dict(project)


def _clean_list(values: list[str]) -> list[str]:
    """Voci ripulite, senza vuoti: una riga bianca nella UI non e' una voce."""
    return [" ".join(str(value).split()) for value in values if str(value).strip()]


def get_project(project_id: str) -> dict | None:
    with workspace_connection() as session:
        project = tenant_row(session, WorkspaceProject, project_id)
        return project_to_dict(project) if project else None


def list_project_processes(project_id: str) -> list[dict]:
    with workspace_connection() as session:
        if tenant_row(session, WorkspaceProject, project_id) is None:
            return []

        statement = (
            select(WorkspaceProcess)
            .where(WorkspaceProcess.project_id == project_id)
            .where(WorkspaceProcess.tenant_id == tenant_id())
            .order_by(WorkspaceProcess.name)
        )
        processes = session.execute(statement).scalars().all()
        return [process_to_dict(process) for process in processes]


def create_process(
    project_id: str,
    name: str,
    stage: str = "AS-IS",
    status: str = "Bozza",
    owner: str = "Da assegnare",
    readiness: int = 0,
) -> dict:
    with workspace_connection() as session:
        current_tenant_id = tenant_id()
        project = tenant_row(session, WorkspaceProject, project_id)

        if project is None:
            raise ValueError(f"Progetto non trovato: {project_id}")

        process_id = unique_id(session, WorkspaceProcess, slugify(name, "process"))
        bpmn_model_id = unique_id(session, WorkspaceBpmnModel, f"{process_id}-bpmn")
        process = WorkspaceProcess(
            id=process_id,
            tenant_id=current_tenant_id,
            project_id=project_id,
            bpmn_model_id=bpmn_model_id,
            name=name.strip(),
            stage=stage.strip() or "AS-IS",
            status=status.strip() or "Bozza",
            owner=owner.strip() or "Da assegnare",
            readiness=max(0, min(int(readiness), 100)),
        )
        session.add(process)
        session.add(
            WorkspaceBpmnModel(
                id=bpmn_model_id,
                tenant_id=current_tenant_id,
                process_id=process_id,
                name=f"{process.name} BPMN",
                xml=None,
            )
        )
        session.flush()
        project.process_count = session.scalar(
            select(func.count())
            .select_from(WorkspaceProcess)
            .where(WorkspaceProcess.project_id == project_id)
            .where(WorkspaceProcess.tenant_id == current_tenant_id)
        ) or 0
        return process_to_dict(process)


def get_process(process_id: str) -> dict | None:
    with workspace_connection() as session:
        process = tenant_row(session, WorkspaceProcess, process_id)
        return process_to_dict(process) if process else None


def get_bpmn_model(bpmn_model_id: str) -> dict | None:
    with workspace_connection() as session:
        model = tenant_row(session, WorkspaceBpmnModel, bpmn_model_id)

        if model is None:
            return None

        return {
            "id": model.id,
            "process_id": model.process_id,
            "name": model.name,
            "xml": model.xml,
        }


def bpmn_version_to_dict(version: WorkspaceBpmnVersion) -> dict:
    return {
        "id": version.id,
        "bpmn_model_id": version.bpmn_model_id,
        "process_id": version.process_id,
        "xml": version.xml,
        "change_summary": version.change_summary,
        "source": version.source,
        "created_at": version.created_at,
    }


def create_bpmn_version(
    session,
    model: WorkspaceBpmnModel,
    xml: str,
    change_summary: str,
    source: str,
) -> WorkspaceBpmnVersion:
    assert_write_allowed("create_bpmn_version")
    version = WorkspaceBpmnVersion(
        tenant_id=getattr(model, "tenant_id", tenant_id()),
        bpmn_model_id=model.id,
        process_id=model.process_id,
        xml=xml,
        change_summary=change_summary.strip() or "Aggiornamento BPMN",
        source=source.strip() or "manual",
        created_at=now_iso(),
    )
    session.add(version)
    return version


def update_bpmn_model(
    bpmn_model_id: str,
    xml: str,
    change_summary: str = "Salvataggio canvas",
    source: str = "manual_save",
) -> dict | None:
    assert_write_allowed("update_bpmn_model")
    with workspace_connection() as session:
        model = tenant_row(session, WorkspaceBpmnModel, bpmn_model_id)

        if model is None:
            return None

        clean_xml = xml.strip()
        if not clean_xml:
            raise ValueError("XML BPMN obbligatorio.")

        model.xml = clean_xml
        create_bpmn_version(
            session=session,
            model=model,
            xml=clean_xml,
            change_summary=change_summary,
            source=source,
        )
        session.flush()
        return {
            "id": model.id,
            "process_id": model.process_id,
            "name": model.name,
            "xml": model.xml,
        }


def list_bpmn_versions(bpmn_model_id: str) -> list[dict]:
    with workspace_connection() as session:
        if tenant_row(session, WorkspaceBpmnModel, bpmn_model_id) is None:
            return []

        statement = (
            select(WorkspaceBpmnVersion)
            .where(WorkspaceBpmnVersion.bpmn_model_id == bpmn_model_id)
            .where(WorkspaceBpmnVersion.tenant_id == tenant_id())
            .order_by(WorkspaceBpmnVersion.id.desc())
        )
        versions = session.execute(statement).scalars().all()
        return [bpmn_version_to_dict(version) for version in versions]


def restore_bpmn_version(bpmn_model_id: str, version_id: int) -> dict:
    assert_write_allowed("restore_bpmn_version")
    with workspace_connection() as session:
        model = tenant_row(session, WorkspaceBpmnModel, bpmn_model_id)
        version = session.get(WorkspaceBpmnVersion, version_id)

        if model is None:
            raise ValueError(f"Modello BPMN non trovato: {bpmn_model_id}")
        if (
            version is None
            or version.bpmn_model_id != bpmn_model_id
            or getattr(version, "tenant_id", "local") != tenant_id()
        ):
            raise ValueError(f"Versione BPMN non trovata: {version_id}")

        model.xml = version.xml
        restored = create_bpmn_version(
            session=session,
            model=model,
            xml=version.xml,
            change_summary=f"Ripristino versione {version_id}",
            source="restore",
        )
        session.flush()
        return {
            "bpmn_model": {
                "id": model.id,
                "process_id": model.process_id,
                "name": model.name,
                "xml": model.xml,
            },
            "restored_from": bpmn_version_to_dict(version),
            "created_version": bpmn_version_to_dict(restored),
        }


def _open_missing_information(review) -> list[str]:
    """`missing_information` minus the points the consultant has already settled.

    Leaving an answered question in the list is not just noise: the list feeds the
    canvas-handoff prerequisite, so a decision the user already made would keep
    the canvas closed forever.
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
    parsed = json.loads(getattr(review, "answers_json", "[]") or "[]")
    return parsed if isinstance(parsed, list) else []


def unanswered_questions(review) -> list[dict]:
    """The gaps still waiting on a human decision."""
    return [item for item in open_questions_with_answers(review) if not item.get("answer")]


def open_questions_with_answers(review) -> list[dict]:
    """The plan's open questions, each with its alternatives and its answer.

    `missing_information` is a flat list of strings: readable, but nothing a
    consultant can act on. These are the same gaps as objects - the alternatives
    the agent proposed, and what was chosen - so a question can actually be
    closed instead of only reported.
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
    """Record what the consultant decided about one open question.

    The answer is stored, not interpreted: turning "the admin office approves it"
    into a changed process model is the agent's work, through
    `revise_bpmn_review`. Keeping the two apart means the human decision survives
    whatever the model does with it next, and stays visible in the history.
    """
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


def _review_artifacts(review) -> tuple[dict, dict]:
    """(semantic model, quality report) from a stored review row.

    Raises when the stored payload is not canonical: a review whose semantic model
    lost its compilation plan or its source understanding cannot be reasoned about,
    and must not be silently reported as a usable plan.
    """
    bpmn_semantic_model = json.loads(review.bpmn_semantic_model_json or "{}")
    if not _is_canonical_semantic_model_payload(bpmn_semantic_model):
        raise ValueError("Review BPMN legacy rifiutata: semantic model non canonicale.")
    process_understanding = bpmn_semantic_model.get("sourceProcessUnderstanding") or {}
    quality_report = quality_report_from_understanding(
        ProcessUnderstanding.model_validate(process_understanding)
    ).model_dump(mode="json")
    return bpmn_semantic_model, quality_report


def review_version_to_dict(version: WorkspaceBpmnReviewVersion) -> dict:
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
    """Snapshot the review as it stands now, under its current version number."""
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
        answers_json=getattr(review, "answers_json", "[]") or "[]",
        status=review.status,
        change_summary=change_summary,
        source=source,
        created_at=now_iso(),
    )
    session.add(version)
    return version


def _mark_review_version_approved(session, review: WorkspaceBpmnReview) -> None:
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
    """Every recorded state of this review, newest first."""
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
        "open_questions": open_questions_with_answers(review),
        "answers": decode_answers(review),
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
    """Edit the narrative of the plan only.

    This is the reader-facing rendering: it does not change what the canvas would
    be generated from. To correct the *content* of the plan, revise the
    ProcessUnderstanding through `revise_bpmn_review`, which regenerates this text
    along with everything derived from it.
    """
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


def prepare_bpmn_review(
    bpmn_model_id: str,
    process_description: str,
    process_understanding: dict | None = None,
) -> dict:
    clean_text = process_description.strip()
    if not clean_text:
        raise ValueError("Descrizione processo obbligatoria.")

    with workspace_connection() as session:
        current_tenant_id = tenant_id()
        model = tenant_row(session, WorkspaceBpmnModel, bpmn_model_id)

        if model is None:
            raise ValueError(f"Modello BPMN non trovato: {bpmn_model_id}")

        bpmn_process_id = f"Process_{slugify(model.process.name, 'process').replace('-', '_')}"
        review_draft = build_bpmn_review_draft(
            bpmn_process_id=bpmn_process_id,
            process_name=model.process.name,
            source_text=clean_text,
            process_understanding=process_understanding,
        )

        timestamp = now_iso()
        review = session.get(WorkspaceBpmnReview, bpmn_model_id)
        if review is not None and getattr(review, "tenant_id", "local") != current_tenant_id:
            review = None

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
            review.status = "pending"
            review.updated_at = timestamp

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
    """Rebuild the plan from a corrected ProcessUnderstanding, as a new version.

    The only editable thing used to be `bpmn_brief`, which is *rendered from* the
    understanding - correcting it changed the text the consultant reads and nothing
    the canvas is generated from, so the next approval quietly ignored the
    correction. Revising the understanding regenerates brief, semantic model,
    readiness and quality together, which is what "edit the plan" has to mean.
    """
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

        xml, _layout_report = optimize_bpmn_layout(bpmn_xml_from_review(
            bpmn_semantic_model_json=review.bpmn_semantic_model_json,
        ))
        model.xml = xml
        approved_version = int(getattr(review, "version", 1) or 1)
        create_bpmn_version(
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
        # Approving does not change what the plan says, only its standing, so the
        # recorded version is marked rather than duplicated.
        _mark_review_version_approved(session, review)
        review_payload = review_to_dict(review)
        session.flush()
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
    """Reasons a BPMN review must not be auto-approved: the quality evaluator did
    not clear it, or the compiled model has a control-flow soundness error.

    `open_questions_pending=False` says every question the plan raised has been
    answered. A `needs_user_clarification` verdict then has nothing left to wait
    for: keeping it as a blocker is how a plan stayed unapprovable no matter how
    many questions the consultant closed.
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


def source_to_dict(source: WorkspaceSource) -> dict:
    return {
        "id": source.id,
        "project_id": source.project_id,
        "process_id": source.process_id,
        "name": source.name,
        "type": source.type,
        "meta": source.meta,
    }


def decision_to_dict(decision: WorkspaceDecision) -> dict:
    return {
        "id": decision.id,
        "project_id": decision.project_id,
        "process_id": decision.process_id,
        "title": decision.title,
        "owner": decision.owner,
        "status": decision.status,
    }


def list_project_sources(project_id: str) -> list[dict]:
    with workspace_connection() as session:
        if tenant_row(session, WorkspaceProject, project_id) is None:
            return []

        statement = (
            select(WorkspaceSource)
            .where(WorkspaceSource.project_id == project_id)
            .where(WorkspaceSource.tenant_id == tenant_id())
            .order_by(WorkspaceSource.name)
        )
        sources = session.execute(statement).scalars().all()
        return [source_to_dict(source) for source in sources]


def create_project_source(
    project_id: str,
    name: str,
    type: str,
    meta: str = "",
    process_id: str | None = None,
) -> dict:
    with workspace_connection() as session:
        current_tenant_id = tenant_id()
        if tenant_row(session, WorkspaceProject, project_id) is None:
            raise ValueError(f"Progetto non trovato: {project_id}")

        if process_id:
            process = tenant_row(session, WorkspaceProcess, process_id)
            if process is None or process.project_id != project_id:
                raise ValueError(f"Processo non trovato: {process_id}")

        source_id = unique_id(session, WorkspaceSource, f"src-{slugify(name, 'source')}")
        source = WorkspaceSource(
            id=source_id,
            tenant_id=current_tenant_id,
            project_id=project_id,
            process_id=process_id,
            name=name.strip(),
            type=type.strip() or "Fonte",
            meta=meta.strip(),
        )
        session.add(source)
        session.flush()
        return source_to_dict(source)


def list_project_decisions(project_id: str) -> list[dict]:
    with workspace_connection() as session:
        if tenant_row(session, WorkspaceProject, project_id) is None:
            return []

        statement = (
            select(WorkspaceDecision)
            .where(WorkspaceDecision.project_id == project_id)
            .where(WorkspaceDecision.tenant_id == tenant_id())
            .order_by(WorkspaceDecision.title)
        )
        decisions = session.execute(statement).scalars().all()
        return [decision_to_dict(decision) for decision in decisions]


def create_project_decision(
    project_id: str,
    title: str,
    owner: str = "Da assegnare",
    status: str = "Aperta",
    process_id: str | None = None,
) -> dict:
    with workspace_connection() as session:
        current_tenant_id = tenant_id()
        if tenant_row(session, WorkspaceProject, project_id) is None:
            raise ValueError(f"Progetto non trovato: {project_id}")

        if process_id:
            process = tenant_row(session, WorkspaceProcess, process_id)
            if process is None or process.project_id != project_id:
                raise ValueError(f"Processo non trovato: {process_id}")

        decision_id = unique_id(session, WorkspaceDecision, f"dec-{slugify(title, 'decision')}")
        decision = WorkspaceDecision(
            id=decision_id,
            tenant_id=current_tenant_id,
            project_id=project_id,
            process_id=process_id,
            title=title.strip(),
            owner=owner.strip() or "Da assegnare",
            status=status.strip() or "Aperta",
        )
        session.add(decision)
        session.flush()
        return decision_to_dict(decision)


def reset_workspace() -> None:
    with workspace_connection() as session:
        current_tenant_id = tenant_id()
        for model in (
            WorkspaceSource,
            WorkspaceDecision,
            WorkspaceSimulationRun,
            WorkspaceBpmnReview,
            WorkspaceBpmnVersion,
            WorkspaceBpmnModel,
            WorkspaceProcess,
            WorkspaceProject,
            WorkspaceClient,
        ):
            for row in session.execute(
                select(model).where(model.tenant_id == current_tenant_id)
            ).scalars():
                session.delete(row)
