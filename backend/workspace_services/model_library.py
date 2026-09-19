"""La libreria dei modelli: ogni disegno BPMN del workspace, con il suo stato.

La sezione Modelli era un segnaposto "in arrivo". I modelli pero' esistono
gia' tutti - uno per processo - e l'unico modo di trovarli era aprire cliente,
progetto e processo uno per uno. Qui si leggono insieme, con cio' che serve per
decidere quale riaprire: se c'e' un disegno, quante versioni ha, a che punto e'
la review e se il confronto con le fonti regge.

Sola lettura. Niente XML: la lista non lo mostra, e su un workspace vero
caricare ogni diagramma per sapere se esiste costerebbe piu' della lista.
"""

from __future__ import annotations

import json

from sqlalchemy import func, select

from backend.security import get_current_tenant_id
from backend.workspace_storage import (
    WorkspaceBpmnModel,
    WorkspaceBpmnReview,
    WorkspaceBpmnVersion,
    WorkspaceClient,
    WorkspaceProcess,
    WorkspaceProject,
    workspace_connection,
)


def _conformance(raw: str | None) -> tuple[str | None, int]:
    """Verdetto e numero di rilievi dell'ultimo confronto registrato.

    Un rapporto illeggibile vale come "mai confrontato": la lista non deve
    cadere per una riga scritta male, e il pannello del processo lo dice meglio.
    """
    if not raw:
        return None, 0
    try:
        report = json.loads(raw)
    except (TypeError, ValueError):
        return None, 0
    if not isinstance(report, dict):
        return None, 0
    verdict = report.get("verdict")
    findings = report.get("findings")
    return (
        verdict if isinstance(verdict, str) else None,
        len(findings) if isinstance(findings, list) else 0,
    )


def list_models() -> list[dict]:
    """I modelli BPMN dei processi attivi del tenant, dal piu' recente.

    Restano fuori i processi archiviati e quelli sotto un progetto o un cliente
    archiviato: l'archivio ha la sua pagina, e qui si cerca il lavoro in corso.

    Returns:
        Una riga per modello, con processo, progetto, cliente, stato del disegno,
        della review e del confronto con le fonti.
    """
    tenant = get_current_tenant_id()

    versions = (
        select(
            WorkspaceBpmnVersion.bpmn_model_id.label("bpmn_model_id"),
            func.count(WorkspaceBpmnVersion.id).label("version_count"),
            func.max(WorkspaceBpmnVersion.created_at).label("last_saved_at"),
        )
        .where(WorkspaceBpmnVersion.tenant_id == tenant)
        .group_by(WorkspaceBpmnVersion.bpmn_model_id)
        .subquery()
    )

    statement = (
        select(
            WorkspaceBpmnModel.id,
            WorkspaceBpmnModel.name,
            # La lunghezza e non l'XML: basta a dire se il disegno esiste.
            func.coalesce(func.length(WorkspaceBpmnModel.xml), 0).label("xml_length"),
            WorkspaceProcess.id.label("process_id"),
            WorkspaceProcess.name.label("process_name"),
            WorkspaceProcess.stage.label("process_stage"),
            WorkspaceProject.id.label("project_id"),
            WorkspaceProject.name.label("project_name"),
            WorkspaceClient.id.label("client_id"),
            WorkspaceClient.name.label("client_name"),
            WorkspaceBpmnReview.status.label("review_status"),
            WorkspaceBpmnReview.version.label("review_version"),
            WorkspaceBpmnReview.readiness_score,
            WorkspaceBpmnReview.updated_at.label("review_updated_at"),
            WorkspaceBpmnReview.conformance_json,
            WorkspaceBpmnReview.conformance_status,
            versions.c.version_count,
            versions.c.last_saved_at,
        )
        .join(WorkspaceProcess, WorkspaceProcess.id == WorkspaceBpmnModel.process_id)
        .join(WorkspaceProject, WorkspaceProject.id == WorkspaceProcess.project_id)
        .join(WorkspaceClient, WorkspaceClient.id == WorkspaceProject.client_id)
        .outerjoin(
            WorkspaceBpmnReview,
            (WorkspaceBpmnReview.bpmn_model_id == WorkspaceBpmnModel.id)
            & (WorkspaceBpmnReview.tenant_id == tenant),
        )
        .outerjoin(versions, versions.c.bpmn_model_id == WorkspaceBpmnModel.id)
        .where(WorkspaceBpmnModel.tenant_id == tenant)
        .where(WorkspaceProcess.tenant_id == tenant)
        .where(WorkspaceProcess.archived_at.is_(None))
        .where(WorkspaceProject.archived_at.is_(None))
        .where(WorkspaceClient.archived_at.is_(None))
    )

    with workspace_connection() as session:
        rows = session.execute(statement).mappings().all()

    models = []
    for row in rows:
        verdict, findings = _conformance(row["conformance_json"])
        models.append(
            {
                "bpmn_model_id": row["id"],
                "name": row["name"],
                "has_diagram": bool(row["xml_length"]),
                "version_count": int(row["version_count"] or 0),
                "last_saved_at": row["last_saved_at"],
                "process_id": row["process_id"],
                "process_name": row["process_name"],
                "process_stage": row["process_stage"],
                "project_id": row["project_id"],
                "project_name": row["project_name"],
                "client_id": row["client_id"],
                "client_name": row["client_name"],
                "review_status": row["review_status"],
                "review_version": row["review_version"],
                "readiness_score": row["readiness_score"],
                "review_updated_at": row["review_updated_at"],
                "conformance_verdict": verdict,
                "conformance_findings": findings,
                "conformance_pending": row["conformance_status"] == "pending",
            }
        )

    # Dal piu' recente: cio' che si e' toccato ieri e' cio' che si riapre oggi.
    # Un modello mai salvato ne' rivisto va in fondo, non in cima per caso.
    def _touched(model: dict) -> str:
        return max(model["last_saved_at"] or "", model["review_updated_at"] or "")

    models.sort(key=lambda model: model["name"].casefold())
    models.sort(key=_touched, reverse=True)
    return models
