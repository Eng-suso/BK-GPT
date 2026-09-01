import json
import re
from datetime import UTC, datetime

from sqlalchemy import func, select, text

from backend.process_understanding import ProcessUnderstanding, quality_report_from_understanding
from backend.security import get_current_tenant_id
from backend.workspace_services.bpmn_review import build_bpmn_review_draft, bpmn_xml_from_review
from backend.workspace_services.bpmn_canvas_edit import optimize_bpmn_layout
from backend.workspace_storage import (
    DATA_DIR,
    WorkspaceBase,
    WorkspaceBpmnModel,
    WorkspaceBpmnReview,
    WorkspaceBpmnVersion,
    WorkspaceClient,
    WorkspaceDecision,
    WorkspaceProcess,
    WorkspaceProject,
    WorkspaceSimulationRun,
    WorkspaceSource,
    workspace_connection,
    workspace_engine,
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


def create_client(
    name: str,
    sector: str = "Non specificato",
    status: str = "Prospect",
    owner: str = "Da assegnare",
    contact: str = "",
) -> dict:
    clean_name = name.strip()

    if not clean_name:
        raise ValueError("Il nome cliente è obbligatorio.")

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
            return client_to_dict(existing_client)

        client_id = unique_id(session, WorkspaceClient, slugify(clean_name, "client"))
        client = WorkspaceClient(
            id=client_id,
            tenant_id=current_tenant_id,
            name=clean_name,
            sector=sector.strip() or "Non specificato",
            status=status.strip() or "Prospect",
            owner=owner.strip() or "Da assegnare",
            contact=contact.strip(),
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
    phase: str = "Discovery",
    status: str = "Bozza",
    progress: int = 0,
    next_step: str = "Definire perimetro e fonti iniziali",
    milestones: list[str] | None = None,
    open_issues: list[str] | None = None,
    deliverables: list[str] | None = None,
) -> dict:
    with workspace_connection() as session:
        current_tenant_id = tenant_id()
        client = tenant_row(session, WorkspaceClient, client_id)

        if client is None:
            raise ValueError(f"Cliente non trovato: {client_id}")

        project_id = unique_id(session, WorkspaceProject, slugify(name, "project"))
        project = WorkspaceProject(
            id=project_id,
            tenant_id=current_tenant_id,
            client_id=client_id,
            name=name.strip(),
            phase=phase.strip() or "Discovery",
            status=status.strip() or "Bozza",
            progress=max(0, min(int(progress), 100)),
            process_count=0,
            next_step=next_step.strip() or "Definire prossimo step",
            milestones_json=encode_list(milestones or []),
            open_issues_json=encode_list(open_issues or []),
            deliverables_json=encode_list(deliverables or []),
        )
        session.add(project)
        session.flush()
        return project_to_dict(project)


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


def review_to_dict(review: WorkspaceBpmnReview) -> dict:
    bpmn_semantic_model = json.loads(review.bpmn_semantic_model_json or "{}")
    if not _is_canonical_semantic_model_payload(bpmn_semantic_model):
        raise ValueError("Review BPMN legacy rifiutata: semantic model non canonicale.")
    process_understanding = bpmn_semantic_model.get("sourceProcessUnderstanding") or {}
    quality_report = quality_report_from_understanding(
        ProcessUnderstanding.model_validate(process_understanding)
    ).model_dump(mode="json")
    return {
        "bpmn_model_id": review.bpmn_model_id,
        "process_id": review.process_id,
        "source_text": review.source_text,
        "process_understanding": process_understanding,
        "bpmn_semantic_model": bpmn_semantic_model,
        "quality_report": quality_report,
        "bpmn_brief": review.bpmn_brief,
        "readiness_score": review.readiness_score,
        "missing_information": decode_list(review.missing_information_json),
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
            review.source_text = review_draft.source_text
            review.process_understanding_json = review_draft.process_understanding_json()
            review.bpmn_semantic_model_json = review_draft.bpmn_semantic_model_json()
            review.bpmn_brief = review_draft.bpmn_brief
            review.readiness_score = review_draft.readiness_score
            review.missing_information_json = encode_list(review_draft.missing_information)
            review.status = "pending"
            review.updated_at = timestamp

        session.flush()
        return review_to_dict(review)


def approve_bpmn_review(bpmn_model_id: str) -> dict:
    with workspace_connection() as session:
        model = tenant_row(session, WorkspaceBpmnModel, bpmn_model_id)
        review = tenant_row(session, WorkspaceBpmnReview, bpmn_model_id)

        if model is None:
            raise ValueError(f"Modello BPMN non trovato: {bpmn_model_id}")
        if review is None:
            raise ValueError("Nessuna review BPMN pronta da approvare per questo canvas.")

        xml, _layout_report = optimize_bpmn_layout(bpmn_xml_from_review(
            bpmn_semantic_model_json=review.bpmn_semantic_model_json,
        ))
        model.xml = xml
        create_bpmn_version(
            session=session,
            model=model,
            xml=xml,
            change_summary="Generazione da review BPMN approvata",
            source="review_approval",
        )
        review.status = "approved"
        review.updated_at = now_iso()
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


def init_workspace_db() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    WorkspaceBase.metadata.create_all(workspace_engine)
    ensure_workspace_schema()


def ensure_workspace_schema() -> None:
    # Su Postgres lo schema lo costruisce interamente `create_all`: le patch
    # incrementali qui sotto (PRAGMA table_info) servono solo al vecchio file
    # SQLite gia' popolato.
    if workspace_engine.dialect.name != "sqlite":
        return
    with workspace_engine.begin() as connection:
        tenant_tables = (
            "workspace_clients",
            "workspace_projects",
            "workspace_processes",
            "workspace_bpmn_models",
            "workspace_bpmn_versions",
            "workspace_bpmn_reviews",
            "workspace_simulation_runs",
            "workspace_sources",
            "workspace_decisions",
        )
        for table_name in tenant_tables:
            columns = {
                row[1]
                for row in connection.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
            }
            if "tenant_id" not in columns:
                connection.execute(
                    text(f"ALTER TABLE {table_name} ADD COLUMN tenant_id VARCHAR NOT NULL DEFAULT 'local'")
                )

        simulation_columns = {
            row[1]
            for row in connection.execute(
                text("PRAGMA table_info(workspace_simulation_runs)")
            ).fetchall()
        }
        if "idempotency_key" not in simulation_columns:
            connection.execute(
                text("ALTER TABLE workspace_simulation_runs ADD COLUMN idempotency_key VARCHAR")
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_workspace_simulation_runs_idempotency_key "
                    "ON workspace_simulation_runs (idempotency_key)"
                )
            )

        review_columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(workspace_bpmn_reviews)")).fetchall()
        }
        if "process_understanding_json" not in review_columns:
            connection.execute(
                text(
                    "ALTER TABLE workspace_bpmn_reviews "
                    "ADD COLUMN process_understanding_json TEXT NOT NULL DEFAULT '{}'"
                )
            )
        if "bpmn_semantic_model_json" not in review_columns:
            connection.execute(
                text(
                    "ALTER TABLE workspace_bpmn_reviews "
                    "ADD COLUMN bpmn_semantic_model_json TEXT NOT NULL DEFAULT '{}'"
                )
            )
        if "status" not in review_columns:
            connection.execute(
                text(
                    "ALTER TABLE workspace_bpmn_reviews "
                    "ADD COLUMN status VARCHAR NOT NULL DEFAULT 'pending'"
                )
            )


init_workspace_db()
