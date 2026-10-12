"""Il cruscotto del responsabile del processo e il suo link privato, sul database vero.

Il cliente non usa DeliR: apre un link. Questi test fissano cosa quel link
mostra (solo il cruscotto, senza note interne ne' citazioni), quando smette di
funzionare (revocato, sostituito, scaduto, processo archiviato) e che il codice
non resta mai in chiaro nel database.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update

from backend.security import reset_current_tenant_id, set_current_tenant_id
from backend.settings import settings
from backend.workspace_services.owner_dashboard import (
    DashboardNotFound, build_owner_dashboard, create_owner_link, open_shared_dashboard, owner_link_status,
    public_process_xml, revoke_owner_link,
)
from backend.workspace_storage import (
    WorkspaceBpmnModel, WorkspaceBpmnVersion, WorkspaceClient, WorkspaceImpactReviewAction, WorkspaceOwnerDashboardLink,
    WorkspaceProcess, WorkspaceProject, WorkspaceSimulationRun, WorkspaceSimulationRunArtifact, workspace_connection,
)

pytestmark = pytest.mark.skipif(not settings.workspace_database_url, reason="requires an isolated workspace Postgres")

XML = """<b:definitions xmlns:b="http://www.omg.org/spec/BPMN/20100524/MODEL" xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:delir="https://delir.example/ext" delir:internal="segreto">
<b:process id="P" isExecutable="false">
<b:startEvent id="start" name="Serve un acquisto"/>
<b:userTask id="approve" name="Approvare richiesta" delir:note="nota interna">
<b:documentation>DeliR traceability: {"source_refs":["steps:approve"]} Nota del consulente: il cliente e' in ritardo</b:documentation>
<b:extensionElements><delir:cost value="riservato"/></b:extensionElements>
</b:userTask>
<b:exclusiveGateway id="amount" name="Importo sopra 5.000 €?"/>
<b:endEvent id="end" name="Ordine inviato"/>
<b:sequenceFlow id="f1" sourceRef="start" targetRef="approve"/>
<b:sequenceFlow id="f2" sourceRef="approve" targetRef="amount"/>
<b:sequenceFlow id="f3" sourceRef="amount" targetRef="end" name="Sì"><b:conditionExpression>${amount &gt; 5000}</b:conditionExpression></b:sequenceFlow>
<b:textAnnotation id="note"><b:text>Da non mostrare al cliente</b:text></b:textAnnotation>
<b:association id="a1" sourceRef="approve" targetRef="note"/>
</b:process>
<bpmndi:BPMNDiagram id="D"><bpmndi:BPMNPlane id="Plane" bpmnElement="P"/></bpmndi:BPMNDiagram>
</b:definitions>"""


@pytest.fixture()
def process():
    identity = uuid.uuid4().hex
    tenant = f"owner-dashboard-{identity}"
    context = set_current_tenant_id(tenant)
    run_ids: list[int] = []
    try:
        with workspace_connection() as session:
            client = WorkspaceClient(id=f"c-{identity}", tenant_id=tenant, name="Azienda demo", sector="Test", status="Attivo", owner="Test", contact="")
            project = WorkspaceProject(id=f"p-{identity}", tenant_id=tenant, client=client, name="Acquisti", lead="Giulia Bianchi", phase="TO-BE", status="In corso", progress=0, process_count=1, next_step="", milestones_json="[]", open_issues_json="[]", deliverables_json="[]")
            process = WorkspaceProcess(id=identity, tenant_id=tenant, project=project, bpmn_model_id=f"b-{identity}", name="Acquisti indiretti", stage="TO-BE", status="Da validare", owner="Amministrazione", readiness=80)
            process.bpmn_model = WorkspaceBpmnModel(id=process.bpmn_model_id, tenant_id=tenant, name="Acquisti indiretti", xml=XML)
            session.add(client)
            session.flush()
            for kind, title, detail in (
                ("candidate", "Togliere la seconda firma sotto 5.000 €", "Due firme anche per importi bassi."),
                ("clarification", "Chi firma sopra 50.000 €?", "Dettaglio interno della domanda"),
                ("deferred", "Fornitori esteri", "Motivo interno del rinvio"),
                ("as_is_proposal", "Correzione del disegno attuale", "Interna"),
            ):
                session.add(WorkspaceImpactReviewAction(
                    id=str(uuid.uuid4()), tenant_id=tenant, process_id=identity, node_id="approve", node_name="Approvare richiesta",
                    base_revision="r", kind=kind, title=title, detail=detail, created_at="2026-10-05T10:00:00+00:00", created_by="consulente",
                ))
            session.add(WorkspaceBpmnVersion(tenant_id=tenant, bpmn_model_id=process.bpmn_model_id, process_id=identity, xml=XML, change_summary="Nuova approvazione", source="canvas", created_at="2026-10-06T09:00:00+00:00"))
            for completed_at, perCase in (("2026-10-01T10:00:00+00:00", 90.0), ("2026-10-06T10:00:00+00:00", 45.0)):
                run = WorkspaceSimulationRun(
                    tenant_id=tenant, bpmn_model_id=process.bpmn_model_id, process_id=identity, scenario_name=f"Scenario {perCase:.0f}",
                    engine="prosimos", status="completed", request_json="{}", scenario_json="{}", result_json="{}", outputs_json="[]",
                    created_at=completed_at, completed_at=completed_at,
                )
                session.add(run)
                session.flush()
                run_ids.append(run.id)
                session.add(WorkspaceSimulationRunArtifact(run_id=run.id, tenant_id=tenant, created_at=completed_at, summary_json=json.dumps({
                    "cycle": {"avg": 216000}, "waiting": {"avg": 129600}, "cost": {"perCase": perCase},
                })))
        yield identity
    finally:
        with workspace_connection() as session:
            session.execute(delete(WorkspaceSimulationRunArtifact).where(WorkspaceSimulationRunArtifact.run_id.in_(run_ids)))
            session.execute(delete(WorkspaceSimulationRun).where(WorkspaceSimulationRun.id.in_(run_ids)))
            session.execute(delete(WorkspaceBpmnVersion).where(WorkspaceBpmnVersion.process_id == identity))
            session.execute(delete(WorkspaceOwnerDashboardLink).where(WorkspaceOwnerDashboardLink.process_id == identity))
            client = session.get(WorkspaceClient, f"c-{identity}")
            if client:
                session.delete(client)
        reset_current_tenant_id(context)


def test_the_dashboard_carries_only_what_the_owner_should_read(process):
    dashboard = build_owner_dashboard(process)

    assert (dashboard.process.name, dashboard.process.owner, dashboard.process.status) == ("Acquisti indiretti", "Amministrazione", "Da validare")
    assert (dashboard.project_name, dashboard.client_name, dashboard.consultant_name) == ("Acquisti", "Azienda demo", "Giulia Bianchi")
    assert [change.title for change in dashboard.changes] == ["Togliere la seconda firma sotto 5.000 €"]
    assert dashboard.changes[0].detail == "Due firme anche per importi bassi."
    assert sorted(point.kind for point in dashboard.open_points) == ["clarification", "deferred"]
    assert [version.change_summary for version in dashboard.versions] == ["Nuova approvazione"]
    # L'ultima simulazione conclusa, non la prima.
    assert dashboard.results is not None
    assert (dashboard.results.scenario_name, dashboard.results.cost_per_case) == ("Scenario 45", 45.0)

    serialized = dashboard.model_dump_json()
    for private in ("Dettaglio interno", "Motivo interno", "Correzione del disegno", "Nota del consulente", "traceability",
                    "riservato", "nota interna", "segreto", "Da non mostrare", "amount &gt;", "BPMNDiagram", "consulente"):
        assert private not in serialized, private


def test_the_public_diagram_keeps_the_process_and_drops_internal_notes():
    public = public_process_xml(XML)
    assert public is not None
    for kept in ('name="Approvare richiesta"', 'name="Importo sopra 5.000 €?"', 'name="Sì"', 'sourceRef="approve"', 'name="Ordine inviato"'):
        assert kept in public, kept
    for dropped in ("documentation", "extensionElements", "textAnnotation", "association", "conditionExpression", "BPMNDiagram", "delir:", "segreto"):
        assert dropped not in public, dropped
    assert public_process_xml(None) is None
    assert public_process_xml("<broken") is None


def test_link_lifecycle_one_active_link_hash_only_and_view_tracking(process):
    assert owner_link_status(process).active is False
    first = create_owner_link(process, "consulente")
    second = create_owner_link(process, "consulente")

    with workspace_connection() as session:
        rows = session.scalars(select(WorkspaceOwnerDashboardLink).where(WorkspaceOwnerDashboardLink.process_id == process)).all()
    assert len(rows) == 2 and sum(row.revoked_at is None for row in rows) == 1
    assert {row.token_hash for row in rows} == {hashlib.sha256(t.encode()).hexdigest() for t in (first.token, second.token)}
    assert all(first.token not in row.token_hash and second.token not in row.token_hash for row in rows)

    # Il link vecchio non funziona piu', il nuovo si'.
    with pytest.raises(DashboardNotFound):
        open_shared_dashboard(first.token)
    assert open_shared_dashboard(second.token).process.name == "Acquisti indiretti"
    open_shared_dashboard(second.token)
    status = owner_link_status(process)
    assert status.active and status.view_count == 2 and status.last_viewed_at

    revoke_owner_link(process)
    assert owner_link_status(process).active is False
    with pytest.raises(DashboardNotFound):
        open_shared_dashboard(second.token)


def test_expired_archived_foreign_or_malformed_links_do_not_open(process):
    created = create_owner_link(process, "consulente")
    with workspace_connection() as session:
        session.execute(update(WorkspaceOwnerDashboardLink).where(WorkspaceOwnerDashboardLink.process_id == process)
                        .values(expires_at=(datetime.now(UTC) - timedelta(seconds=1)).isoformat()))
    with pytest.raises(DashboardNotFound):
        open_shared_dashboard(created.token)
    assert owner_link_status(process).active is False

    created = create_owner_link(process, "consulente")
    with workspace_connection() as session:
        session.execute(update(WorkspaceProcess).where(WorkspaceProcess.id == process).values(archived_at="2026-10-10T00:00:00+00:00"))
    with pytest.raises(DashboardNotFound):
        open_shared_dashboard(created.token)
    with workspace_connection() as session:
        session.execute(update(WorkspaceProcess).where(WorkspaceProcess.id == process).values(archived_at=None))

    for token in ("", "short", "x" * 300, "../../etc/passwd" + "a" * 40, "a" * 43):
        with pytest.raises(DashboardNotFound):
            open_shared_dashboard(token)

    other = set_current_tenant_id("another-tenant")
    try:
        for call in (lambda: build_owner_dashboard(process), lambda: create_owner_link(process, "x"), lambda: owner_link_status(process), lambda: revoke_owner_link(process)):
            with pytest.raises(DashboardNotFound):
                call()
    finally:
        reset_current_tenant_id(other)


@pytest.fixture()
def api():
    from backend.app import app

    with TestClient(app) as test_client:
        yield test_client


def test_http_link_is_created_by_the_studio_and_read_without_studio_credentials(process, api, monkeypatch):
    tenant = f"owner-dashboard-{process}"
    studio = {"X-DeliR-Tenant-ID": tenant}
    created = api.post(f"/v1/workspace/processes/{process}/owner-link", headers=studio)
    assert created.status_code == 201
    assert created.headers["cache-control"] == "no-store"
    token = created.json()["token"]
    assert api.get(f"/v1/workspace/processes/{process}/owner-link", headers=studio).json()["active"] is True
    preview = api.get(f"/v1/workspace/processes/{process}/owner-dashboard", headers=studio).json()

    # Con l'autenticazione dello studio accesa, il link si legge senza le sue credenziali.
    monkeypatch.setattr(settings, "delir_auth_enabled", True)
    monkeypatch.setattr(settings, "delir_api_token", "studio-secret")
    monkeypatch.setattr(settings, "delir_allowed_tenant_ids", "only-the-studio")
    assert api.get(f"/v1/workspace/processes/{process}/owner-dashboard").status_code in (401, 403)

    shared = api.get("/v1/shared/process-dashboard", headers={"X-DeliR-Share-Token": token})
    assert shared.status_code == 200
    assert shared.headers["cache-control"] == "no-store"
    assert shared.headers["referrer-policy"] == "no-referrer"
    assert "noindex" in shared.headers["x-robots-tag"]
    body = shared.json()
    assert body["process"] == preview["process"] and body["changes"] == preview["changes"] and body["xml"] == preview["xml"]

    for headers in ({}, {"X-DeliR-Share-Token": "a" * 43}, {"X-DeliR-Share-Token": token + "x"}):
        missing = api.get("/v1/shared/process-dashboard", headers=headers)
        assert missing.status_code == 404
        assert missing.json()["error"]["message"] == "Link non valido o scaduto."
        assert missing.headers["cache-control"] == "no-store"
    # Il codice non si legge dall'indirizzo: solo dall'intestazione.
    assert api.get(f"/v1/shared/process-dashboard?token={token}").status_code == 404
