"""Il cruscotto del responsabile del processo, e il link privato per leggerlo.

DeliR lo usano solo i consulenti. Il responsabile del processo presso il
cliente riceve un link: lo apre senza account e vede, in sola lettura, il
processo spiegato passo per passo, cosa cambia, i risultati attesi e cosa sta
succedendo. La stessa costruzione serve l'anteprima del consulente e il link,
cosi' l'anteprima e' davvero cio' che il cliente vede.

Sicurezza del link:
- il codice ha 256 bit casuali ed esiste in chiaro solo nella risposta che lo
  crea; nel database c'e' la sua impronta sha256;
- un processo ha al piu' un link attivo: crearne uno nuovo revoca il vecchio;
- il link scade, si revoca, e smette di funzionare se il processo, il progetto
  o il cliente vengono archiviati;
- il cruscotto non contiene citazioni dalle fonti, note interne del disegno ne'
  il dettaglio delle domande aperte.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from xml.etree.ElementTree import Element, tostring

from defusedxml.ElementTree import fromstring
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.schemas.owner_dashboard import (
    DashboardChange, DashboardOpenPoint, DashboardProcess, DashboardResults, DashboardVersion,
    OwnerDashboard, OwnerLinkCreated, OwnerLinkStatus,
)
from backend.security import get_current_tenant_id, reset_current_tenant_id, set_current_tenant_id
from backend.workspace_storage import (
    WorkspaceBpmnModel, WorkspaceBpmnVersion, WorkspaceImpactReviewAction, WorkspaceOwnerDashboardLink,
    WorkspaceProcess, WorkspaceProject, WorkspaceSimulationRun, WorkspaceSimulationRunArtifact,
    workspace_connection,
)

LINK_LIFETIME = timedelta(days=180)
MAX_VERSIONS = 20
_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
# Cio' che nel disegno e' per il consulente o per il motore, non per il cliente.
_PRIVATE_ELEMENTS = {
    "documentation", "extensionElements", "BPMNDiagram", "textAnnotation", "association", "conditionExpression",
}
_PUBLIC_ATTRIBUTES = {
    "id", "name", "sourceRef", "targetRef", "processRef", "default", "attachedToRef",
    "isInterrupting", "cancelActivity", "gatewayDirection", "isExecutable",
}


class DashboardNotFound(LookupError):
    """Processo inesistente, di un altro spazio di lavoro, archiviato, o link non valido."""


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(moment: datetime) -> str:
    return moment.isoformat()


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _active_process(session: Session, process_id: str, tenant: str) -> WorkspaceProcess:
    process = session.scalar(select(WorkspaceProcess).where(
        WorkspaceProcess.id == process_id, WorkspaceProcess.tenant_id == tenant,
    ))
    if process is None or process.archived_at:
        raise DashboardNotFound("Processo non trovato.")
    project = session.get(WorkspaceProject, process.project_id)
    if project is None or project.tenant_id != tenant or project.archived_at or project.client.archived_at:
        raise DashboardNotFound("Processo non trovato.")
    return process


def public_process_xml(xml: str | None) -> str | None:
    """Il disegno senza note, estensioni, annotazioni, condizioni e coordinate."""
    if not xml:
        return None
    try:
        root = fromstring(xml)
    except Exception:
        return None
    _strip(root)
    return tostring(root, encoding="unicode")


def _strip(element: Element) -> None:
    for name in list(element.attrib):
        if name not in _PUBLIC_ATTRIBUTES:
            del element.attrib[name]
    for child in list(element):
        if child.tag.rsplit("}", 1)[-1] in _PRIVATE_ELEMENTS:
            element.remove(child)
        else:
            _strip(child)


def _results(session: Session, process: WorkspaceProcess, tenant: str) -> DashboardResults | None:
    runs = session.scalars(
        select(WorkspaceSimulationRun)
        .where(WorkspaceSimulationRun.tenant_id == tenant)
        .where(WorkspaceSimulationRun.bpmn_model_id == process.bpmn_model_id)
        .where(WorkspaceSimulationRun.status == "completed")
        .order_by(WorkspaceSimulationRun.completed_at.desc().nulls_last(), WorkspaceSimulationRun.id.desc())
    ).all()
    for run in runs:
        artifact = session.get(WorkspaceSimulationRunArtifact, run.id)
        summary = json.loads(artifact.summary_json or "{}") if artifact else {}
        try:
            return DashboardResults(
                scenario_name=run.scenario_name,
                completed_at=run.completed_at,
                cycle_avg_seconds=float(summary["cycle"]["avg"]),
                waiting_avg_seconds=float(summary["waiting"]["avg"]),
                cost_per_case=float(summary["cost"]["perCase"]),
            )
        except (KeyError, TypeError, ValueError):
            continue
    return None


def _build(session: Session, process: WorkspaceProcess, tenant: str) -> OwnerDashboard:
    project = session.get(WorkspaceProject, process.project_id)
    model = session.scalar(select(WorkspaceBpmnModel).where(
        WorkspaceBpmnModel.id == process.bpmn_model_id, WorkspaceBpmnModel.tenant_id == tenant,
    ))
    actions = session.scalars(select(WorkspaceImpactReviewAction).where(
        WorkspaceImpactReviewAction.process_id == process.id,
        WorkspaceImpactReviewAction.tenant_id == tenant,
    ).order_by(WorkspaceImpactReviewAction.created_at.desc(), WorkspaceImpactReviewAction.id)).all()
    versions = session.scalars(
        select(WorkspaceBpmnVersion)
        .where(WorkspaceBpmnVersion.bpmn_model_id == process.bpmn_model_id, WorkspaceBpmnVersion.tenant_id == tenant)
        .order_by(WorkspaceBpmnVersion.id.desc())
        .limit(MAX_VERSIONS)
    ).all()
    return OwnerDashboard(
        process=DashboardProcess(name=process.name, owner=process.owner, status=process.status, stage=process.stage),
        project_name=project.name if project else "",
        client_name=project.client.name if project else "",
        consultant_name=(project.lead or "").strip() if project else "",
        xml=public_process_xml(model.xml if model else None),
        changes=[
            DashboardChange(id=row.id, node_id=row.node_id, node_name=row.node_name, title=row.title, detail=row.detail, created_at=row.created_at)
            for row in actions if row.kind == "candidate"
        ],
        open_points=[
            DashboardOpenPoint(id=row.id, node_id=row.node_id, node_name=row.node_name, title=row.title, kind=row.kind, created_at=row.created_at)
            for row in actions if row.kind in ("clarification", "deferred")
        ],
        versions=[DashboardVersion(id=row.id, change_summary=row.change_summary, created_at=row.created_at) for row in versions],
        results=_results(session, process, tenant),
        generated_at=_iso(_now()),
    )


def build_owner_dashboard(process_id: str) -> OwnerDashboard:
    """L'anteprima del consulente: lo stesso cruscotto che riceve il cliente."""
    tenant = get_current_tenant_id()
    with workspace_connection() as session:
        return _build(session, _active_process(session, process_id, tenant), tenant)


def _active_link(session: Session, process_id: str, tenant: str) -> WorkspaceOwnerDashboardLink | None:
    now = _iso(_now())
    return session.scalar(
        select(WorkspaceOwnerDashboardLink)
        .where(WorkspaceOwnerDashboardLink.process_id == process_id)
        .where(WorkspaceOwnerDashboardLink.tenant_id == tenant)
        .where(WorkspaceOwnerDashboardLink.revoked_at.is_(None))
        .where(WorkspaceOwnerDashboardLink.expires_at > now)
        .order_by(WorkspaceOwnerDashboardLink.created_at.desc())
    )


def owner_link_status(process_id: str) -> OwnerLinkStatus:
    tenant = get_current_tenant_id()
    with workspace_connection() as session:
        _active_process(session, process_id, tenant)
        link = _active_link(session, process_id, tenant)
        if link is None:
            return OwnerLinkStatus(active=False)
        return OwnerLinkStatus(
            active=True, created_at=link.created_at, expires_at=link.expires_at,
            last_viewed_at=link.last_viewed_at, view_count=link.view_count,
        )


def _revoke_all(session: Session, process_id: str, tenant: str, now: str) -> None:
    session.execute(
        update(WorkspaceOwnerDashboardLink)
        .where(WorkspaceOwnerDashboardLink.process_id == process_id)
        .where(WorkspaceOwnerDashboardLink.tenant_id == tenant)
        .where(WorkspaceOwnerDashboardLink.revoked_at.is_(None))
        .values(revoked_at=now)
    )


def create_owner_link(process_id: str, created_by: str) -> OwnerLinkCreated:
    """Crea il link e revoca quello di prima: un processo ha un solo link attivo."""
    tenant = get_current_tenant_id()
    token = secrets.token_urlsafe(32)
    now = _now()
    with workspace_connection() as session:
        process = _active_process(session, process_id, tenant)
        # Due creazioni insieme non devono lasciare due link attivi.
        session.scalar(select(WorkspaceProcess).where(WorkspaceProcess.id == process.id).with_for_update())
        _revoke_all(session, process_id, tenant, _iso(now))
        link = WorkspaceOwnerDashboardLink(
            id=str(uuid.uuid4()), tenant_id=tenant, process_id=process_id, token_hash=_hash(token),
            created_at=_iso(now), created_by=created_by, expires_at=_iso(now + LINK_LIFETIME), view_count=0,
        )
        session.add(link)
        return OwnerLinkCreated(token=token, created_at=link.created_at, expires_at=link.expires_at)


def revoke_owner_link(process_id: str) -> None:
    tenant = get_current_tenant_id()
    with workspace_connection() as session:
        _active_process(session, process_id, tenant)
        _revoke_all(session, process_id, tenant, _iso(_now()))


def open_shared_dashboard(token: str) -> OwnerDashboard:
    """Il cruscotto dal link. Ogni errore e' lo stesso 'non trovato'."""
    if not _TOKEN_PATTERN.fullmatch(token or ""):
        raise DashboardNotFound("Link non valido.")
    now = _iso(_now())
    with workspace_connection() as session:
        link = session.scalar(select(WorkspaceOwnerDashboardLink).where(WorkspaceOwnerDashboardLink.token_hash == _hash(token)))
        if link is None or link.revoked_at or link.expires_at <= now:
            raise DashboardNotFound("Link non valido.")
        context = set_current_tenant_id(link.tenant_id)
        try:
            process = _active_process(session, link.process_id, link.tenant_id)
            dashboard = _build(session, process, link.tenant_id)
        finally:
            reset_current_tenant_id(context)
        session.execute(
            update(WorkspaceOwnerDashboardLink)
            .where(WorkspaceOwnerDashboardLink.id == link.id)
            .values(last_viewed_at=now, view_count=WorkspaceOwnerDashboardLink.view_count + 1)
        )
        return dashboard
