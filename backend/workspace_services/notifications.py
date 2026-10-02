"""Gli avvisi: cosa e' successo mentre il consulente guardava altrove.

La campanella nella barra in alto mostrava un `3` scritto a mano. Il lavoro vero
pero' succede davvero in differita - un piano si ricostruisce in coda, un
confronto con le fonti gira dopo che il disegno e' uscito, una simulazione
finisce minuti dopo - e senza un posto dove leggerlo il consulente se ne accorge
solo riaprendo il processo giusto per caso.

Gli avvisi si **derivano dai fatti** che il workspace gia' conserva, invece di
essere scritti una seconda volta in un registro di eventi: due verita' che
possono divergere sono una verita' e un bug. L'unica cosa che i fatti non sanno
e' se qualcuno li ha gia' visti, e quella si registra
(`workspace_notification_reads`).

Il testo non si compone qui: il backend dice cosa e' successo e a cosa si
riferisce, la lingua la sceglie l'interfaccia.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Literal

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.security import get_current_tenant_id
from backend.workspace_storage import (
    WorkspaceBpmnReview,
    WorkspaceClient,
    WorkspacePlanMaterialization,
    WorkspaceProcess,
    WorkspaceProject,
    WorkspaceSimulationRun,
    workspace_connection,
)

NotificationKind = Literal[
    "plan_ready",
    "plan_failed",
    "conformance_findings",
    "simulation_done",
    "simulation_failed",
]

# Quanti avvisi leggere per tipo prima di ordinarli insieme. Tiene il costo
# fisso su un workspace grande: la campanella non e' un archivio.
PER_KIND_LIMIT = 20
DEFAULT_LIMIT = 20

# Un confronto che non ha trovato niente non e' un avviso: non c'e' niente da
# fare, e un elenco di buone notizie insegna a non aprirlo.
ACTIONABLE_VERDICTS = {"not_conformant", "incomplete", "conformant_with_divergences"}

# La tabella dello stato di lettura vive qui e non fra i modelli del workspace:
# non e' un record del lavoro, e' una spunta di chi legge.
_metadata = sa.MetaData()
NOTIFICATION_READS = sa.Table(
    "workspace_notification_reads",
    _metadata,
    sa.Column("tenant_id", sa.String, primary_key=True),
    sa.Column("notification_id", sa.String, primary_key=True),
    sa.Column("read_at", sa.String, nullable=False),
)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _report(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        report = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return report if isinstance(report, dict) else {}


def _active(statement, tenant: str):
    """Solo il lavoro in corso: l'archivio ha la sua pagina, e un avviso su un
    incarico chiuso fa riaprire la cosa sbagliata."""
    return (
        statement.where(WorkspaceProcess.tenant_id == tenant)
        .where(WorkspaceProcess.archived_at.is_(None))
        .where(WorkspaceProject.archived_at.is_(None))
        .where(WorkspaceClient.archived_at.is_(None))
    )


def _where(row) -> dict[str, Any]:
    """I campi comuni: di quale processo si parla, e sotto chi sta."""
    return {
        "process_id": row.process_id,
        "process_name": row.process_name,
        "project_id": row.project_id,
        "project_name": row.project_name,
        "client_name": row.client_name,
    }


def _collect(session, tenant: str) -> list[dict]:
    items: list[dict] = []

    plans = session.execute(
        _active(
            sa.select(
                WorkspacePlanMaterialization.status,
                WorkspacePlanMaterialization.completed_at,
                WorkspacePlanMaterialization.requested_at,
                WorkspacePlanMaterialization.plan_version,
                WorkspacePlanMaterialization.last_error,
                WorkspaceProcess.id.label("process_id"),
                WorkspaceProcess.name.label("process_name"),
                WorkspaceProcess.bpmn_model_id.label("bpmn_model_id"),
                WorkspaceProject.id.label("project_id"),
                WorkspaceProject.name.label("project_name"),
                WorkspaceClient.name.label("client_name"),
            )
            .join(WorkspaceProcess, WorkspaceProcess.id == WorkspacePlanMaterialization.process_id)
            .join(WorkspaceProject, WorkspaceProject.id == WorkspaceProcess.project_id)
            .join(WorkspaceClient, WorkspaceClient.id == WorkspaceProject.client_id)
            .where(WorkspacePlanMaterialization.tenant_id == tenant)
            .where(WorkspacePlanMaterialization.status.in_(("done", "failed")))
            .order_by(WorkspacePlanMaterialization.requested_at.desc())
            .limit(PER_KIND_LIMIT),
            tenant,
        )
    ).all()
    for row in plans:
        occurred = row.completed_at or row.requested_at
        ready = row.status == "done"
        items.append(
            {
                "id": f"plan:{row.process_id}:{occurred}",
                "kind": "plan_ready" if ready else "plan_failed",
                "occurred_at": occurred,
                "bpmn_model_id": row.bpmn_model_id,
                "count": 0,
                "version": row.plan_version if ready else None,
                # Il messaggio del guasto, tagliato: serve a capire se riprovare
                # o chiamare qualcuno, non a leggere uno stack trace.
                "detail": "" if ready else (row.last_error or "")[:200],
                **_where(row),
            }
        )

    reviews = session.execute(
        _active(
            sa.select(
                WorkspaceBpmnReview.bpmn_model_id,
                WorkspaceBpmnReview.conformance_json,
                WorkspaceBpmnReview.updated_at,
                WorkspaceProcess.id.label("process_id"),
                WorkspaceProcess.name.label("process_name"),
                WorkspaceProject.id.label("project_id"),
                WorkspaceProject.name.label("project_name"),
                WorkspaceClient.name.label("client_name"),
            )
            .join(WorkspaceProcess, WorkspaceProcess.id == WorkspaceBpmnReview.process_id)
            .join(WorkspaceProject, WorkspaceProject.id == WorkspaceProcess.project_id)
            .join(WorkspaceClient, WorkspaceClient.id == WorkspaceProject.client_id)
            .where(WorkspaceBpmnReview.tenant_id == tenant)
            .where(WorkspaceBpmnReview.conformance_json.is_not(None))
            .order_by(WorkspaceBpmnReview.updated_at.desc())
            .limit(PER_KIND_LIMIT),
            tenant,
        )
    ).all()
    for row in reviews:
        report = _report(row.conformance_json)
        verdict = report.get("verdict")
        if verdict not in ACTIONABLE_VERDICTS:
            continue
        findings = report.get("findings")
        occurred = report.get("audited_at") or row.updated_at
        items.append(
            {
                "id": f"conformance:{row.bpmn_model_id}:{occurred}",
                "kind": "conformance_findings",
                "occurred_at": occurred,
                "bpmn_model_id": row.bpmn_model_id,
                "count": len(findings) if isinstance(findings, list) else 0,
                "version": None,
                "detail": str(verdict),
                **_where(row),
            }
        )

    runs = session.execute(
        _active(
            sa.select(
                WorkspaceSimulationRun.id.label("run_id"),
                WorkspaceSimulationRun.status,
                WorkspaceSimulationRun.scenario_name,
                WorkspaceSimulationRun.completed_at,
                WorkspaceSimulationRun.created_at,
                WorkspaceSimulationRun.error,
                WorkspaceSimulationRun.bpmn_model_id,
                WorkspaceProcess.id.label("process_id"),
                WorkspaceProcess.name.label("process_name"),
                WorkspaceProject.id.label("project_id"),
                WorkspaceProject.name.label("project_name"),
                WorkspaceClient.name.label("client_name"),
            )
            .join(WorkspaceProcess, WorkspaceProcess.id == WorkspaceSimulationRun.process_id)
            .join(WorkspaceProject, WorkspaceProject.id == WorkspaceProcess.project_id)
            .join(WorkspaceClient, WorkspaceClient.id == WorkspaceProject.client_id)
            .where(WorkspaceSimulationRun.tenant_id == tenant)
            .where(WorkspaceSimulationRun.status.in_(("completed", "failed")))
            .order_by(WorkspaceSimulationRun.created_at.desc())
            .limit(PER_KIND_LIMIT),
            tenant,
        )
    ).all()
    for row in runs:
        done = row.status == "completed"
        occurred = row.completed_at or row.created_at
        items.append(
            {
                "id": f"simulation:{row.run_id}",
                "kind": "simulation_done" if done else "simulation_failed",
                "occurred_at": occurred,
                "bpmn_model_id": row.bpmn_model_id,
                "count": 0,
                "version": None,
                "detail": row.scenario_name if done else (row.error or "")[:200],
                "run_id": row.run_id,
                **_where(row),
            }
        )

    return items


def list_notifications(limit: int = DEFAULT_LIMIT) -> dict:
    """Cosa e' successo di recente nel workspace del tenant, dal piu' recente.

    Args:
        limit: Quanti avvisi restituire.

    Returns:
        ``{"items": [...], "unread": n}``. `unread` conta gli avvisi restituiti
        che nessuno ha ancora letto: e' il numero della campanella, e quando e'
        zero la campanella non deve mostrare niente.
    """
    tenant = get_current_tenant_id()

    with workspace_connection() as session:
        items = _collect(session, tenant)
        items.sort(key=lambda item: item["occurred_at"] or "", reverse=True)
        items = items[: max(1, int(limit))]

        read_ids: set[str] = set()
        if items:
            read_ids = {
                row.notification_id
                for row in session.execute(
                    sa.select(NOTIFICATION_READS.c.notification_id)
                    .where(NOTIFICATION_READS.c.tenant_id == tenant)
                    .where(
                        NOTIFICATION_READS.c.notification_id.in_([item["id"] for item in items])
                    )
                ).all()
            }

    for item in items:
        item["read"] = item["id"] in read_ids

    return {"items": items, "unread": sum(1 for item in items if not item["read"])}


def mark_read(notification_ids: list[str]) -> int:
    """Segna come letti gli avvisi indicati.

    Args:
        notification_ids: Gli id degli avvisi, non affidabili. Quelli gia' letti
            non cambiano: la prima lettura e' quella che conta.

    Returns:
        Quanti id sono stati registrati (compresi quelli gia' presenti).
    """
    ids = [str(value) for value in notification_ids if str(value).strip()]
    if not ids:
        return 0

    tenant = get_current_tenant_id()
    now = _now()
    with workspace_connection() as session:
        session.execute(
            pg_insert(NOTIFICATION_READS)
            .values([
                {"tenant_id": tenant, "notification_id": notification_id, "read_at": now}
                for notification_id in ids
            ])
            .on_conflict_do_nothing(index_elements=["tenant_id", "notification_id"])
        )
    return len(ids)


def mark_all_read(limit: int = DEFAULT_LIMIT) -> int:
    """Segna come letto tutto cio' che la campanella sta mostrando.

    Non segna cio' che non e' stato mostrato: "segna tutto come letto" deve
    valere per quello che il consulente ha davanti, altrimenti nasconde avvisi
    che non ha mai visto.
    """
    items = list_notifications(limit=limit)["items"]
    return mark_read([item["id"] for item in items if not item["read"]])
