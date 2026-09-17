"""La revisione per elemento: confermare un'inferenza, o toglierla senza rompere il flusso.

Due parti, perche' sono due garanzie diverse:

1. **la rimozione e' una trasformazione del piano** - senza database: un
   passaggio tolto non lascia riferimenti rotti, i flussi che lo attraversavano
   si ricuciono, le eccezioni sue escono con lui, attori e decisioni non si
   tolgono con un click;
2. **la revisione arriva fino al disegno** - su database vero: una conferma si
   registra e cambia il segno sul canvas salvato senza ridisegnarlo, un rifiuto
   toglie l'elemento dal piano e dal canvas, e una decisione presa su un
   elemento non si applica a un altro che ne ha preso l'id.
"""

from __future__ import annotations

import uuid
import xml.etree.ElementTree as ET

import pytest

from backend.agents.plan_element_removal import ElementNotRemovable, remove_plan_element
from backend.agents.plan_provenance import ElementProvenance, ProvenanceReport
from backend.process_understanding import (
    ProcessDecision,
    ProcessDecisionOutcome,
    ProcessExceptionPath,
    ProcessFlowEdge,
    ProcessLoop,
    ProcessPath,
    ProcessStep,
    ProcessUnderstanding,
)
from backend.settings import settings


def _plan() -> ProcessUnderstanding:
    return ProcessUnderstanding(
        title="Ciclo passivo",
        steps=[
            ProcessStep(id="apri", label="Apri richiesta"),
            ProcessStep(id="audit", label="Audit trimestrale"),
            ProcessStep(id="ordina", label="Emetti ordine"),
            ProcessStep(id="integra", label="Richiedi integrazione"),
        ],
        main_success_path=["apri", "audit", "ordina"],
        flow_edges=[
            ProcessFlowEdge(id="e1", source_id="apri", target_id="audit", label="aperta"),
            ProcessFlowEdge(id="e2", source_id="audit", target_id="ordina", label="auditata"),
        ],
        decisions=[
            ProcessDecision(
                id="esito",
                label="Esito?",
                outcome_details=[
                    ProcessDecisionOutcome(id="o1", label="Procedi", target_ref="audit"),
                ],
            )
        ],
        alternative_paths=[
            ProcessPath(id="p1", label="Integrazione", sequence=["integra"], rejoins_at="audit"),
        ],
        exceptions=[
            ProcessExceptionPath(id="ex", label="Audit bloccato", attached_to_step_id="audit"),
        ],
        loops=[ProcessLoop(id="l1", label="Ripeti audit", repeated_steps=["audit"])],
    )


# --- la rimozione -----------------------------------------------------------


def test_a_removed_step_leaves_no_reference_behind():
    plan = remove_plan_element(_plan(), kind="step", element_id="audit")

    dumped = plan.model_dump_json()
    assert '"audit"' not in dumped
    assert [step.id for step in plan.steps] == ["apri", "ordina", "integra"]
    assert plan.main_success_path == ["apri", "ordina"]


def test_the_flow_through_a_removed_step_is_stitched_back():
    """Togliere un passaggio inventato non deve spezzare il processo in due."""
    plan = remove_plan_element(_plan(), kind="step", element_id="audit")

    assert [(edge.source_id, edge.target_id) for edge in plan.flow_edges] == [("apri", "ordina")]


def test_what_pointed_at_the_removed_step_moves_to_its_single_successor():
    plan = remove_plan_element(_plan(), kind="step", element_id="audit")

    assert plan.decisions[0].outcome_details[0].target_ref == "ordina"
    assert plan.alternative_paths[0].rejoins_at == "ordina"


def test_the_exceptions_and_loops_of_the_removed_step_go_with_it():
    plan = remove_plan_element(_plan(), kind="step", element_id="audit")

    assert plan.exceptions == []
    assert plan.loops == []


def test_the_original_plan_is_not_touched():
    original = _plan()
    before = original.model_dump_json()

    remove_plan_element(original, kind="step", element_id="audit")

    assert original.model_dump_json() == before


@pytest.mark.parametrize("kind", ["actor", "decision", "participant", "flow"])
def test_structure_is_not_removed_with_a_click(kind):
    with pytest.raises(ElementNotRemovable):
        remove_plan_element(_plan(), kind=kind, element_id="esito")


def test_an_element_that_is_not_there_is_refused():
    with pytest.raises(ElementNotRemovable):
        remove_plan_element(_plan(), kind="step", element_id="inesistente")


# --- le decisioni nel rapporto -----------------------------------------------


def _report() -> ProvenanceReport:
    return ProvenanceReport(
        elements=[
            ElementProvenance(
                kind="step", element_id="audit", label="Audit trimestrale",
                status="unverified", source_ref="steps:audit",
            ),
            ElementProvenance(
                kind="step", element_id="apri", label="Apri richiesta",
                status="verified", source_ref="steps:apri",
            ),
        ]
    )


def test_a_confirmed_inference_is_no_longer_awaiting_but_is_still_not_a_quote():
    report = _report().with_decisions(
        {"steps:audit": {"decision": "confirmed", "label": "Audit trimestrale"}}
    )

    audit = report.elements[0]
    assert audit.status == "unverified", "la fonte continua a non dirlo"
    assert audit.mark_status == "confirmed"
    assert report.awaiting_confirmation == []
    assert report.status_by_source_ref()["steps:audit"] == "confirmed"


def test_a_decision_on_another_element_with_the_same_id_does_not_apply():
    """Un piano ricostruito puo' riusare un id: la conferma non passa al nuovo passaggio."""
    report = _report().with_decisions(
        {"steps:audit": {"decision": "confirmed", "label": "Audit annuale dei contratti"}}
    )

    assert report.elements[0].consultant_decision is None
    assert len(report.awaiting_confirmation) == 1


# --- fino al disegno, su database vero ---------------------------------------


needs_db = pytest.mark.skipif(
    not all((settings.workspace_database_url, settings.canonical_database_url)),
    reason="servono WORKSPACE_DATABASE_URL e le DSN canonical",
)


@pytest.fixture()
def drafted_process_with_an_inference():
    from backend.process_understanding import ProcessStep as Step
    from backend.workspace_services.bpmn_draft import generate_bpmn_draft
    from tests.test_process_canvas_handoff_e2e import (
        _bind_process_chat,
        _prepare_plan,
        _save_interviews,
        _supported_understanding,
    )
    from backend import workspace_database as wd
    from backend.security import reset_current_tenant_id, set_current_tenant_id

    token = set_current_tenant_id(f"t-review-{uuid.uuid4().hex[:8]}")
    try:
        client = wd.create_client(name=f"Cliente {uuid.uuid4().hex[:6]}")
        project = wd.create_project(client_id=client["id"], name="Acquisti")
        process = wd.create_process(project_id=project["id"], name="Gestione acquisto materiali indiretti e servizi")
        scope = {
            "project_id": project["id"],
            "process_id": process["id"],
            "bpmn_model_id": process["bpmn_model_id"],
        }
        _save_interviews(scope)
        understanding = _supported_understanding()
        understanding.steps.append(
            Step(
                id="audit_trimestrale",
                label="Audit trimestrale dei fornitori strategici",
                actor_ids=["acquisti"],
            )
        )
        understanding.sequence = ["apri_richiesta", "verifica_autorizzazione", "audit_trimestrale", "crea_ordine"]
        understanding.main_success_path = list(understanding.sequence)
        _prepare_plan(scope, understanding)
        with _bind_process_chat(scope["project_id"], scope["process_id"]):
            drafted = generate_bpmn_draft(scope["process_id"])
        assert drafted.ok, drafted.reason
        yield scope
    finally:
        reset_current_tenant_id(token)


def _node_marks(xml: str) -> dict[str, str]:
    from backend.workspace_services.bpmn_provenance_marks import PROVENANCE_ATTRIBUTE

    root = ET.fromstring(xml)
    return {
        str(element.attrib.get("name")): str(element.attrib.get(PROVENANCE_ATTRIBUTE))
        for element in root.iter()
        if element.attrib.get(PROVENANCE_ATTRIBUTE)
    }


@needs_db
def test_confirming_an_inference_updates_the_saved_canvas_without_redrawing(
    drafted_process_with_an_inference, monkeypatch
):
    from backend import workspace_database as wd
    from backend.workspace_services import element_review

    scope = drafted_process_with_an_inference
    monkeypatch.setattr(settings, "openai_api_key", None)
    # Una modifica a mano sul canvas: la conferma non deve cancellarla.
    before = wd.get_bpmn_model(scope["bpmn_model_id"])["xml"]
    edited = before.replace('name="Apri richiesta di acquisto"', 'name="Apri richiesta di acquisto (modulo)"')
    wd.update_bpmn_model(scope["bpmn_model_id"], edited, change_summary="modifica a mano")
    assert _node_marks(edited)["Audit trimestrale dei fornitori strategici"] == "unverified"

    result = element_review.review_plan_element(
        scope["process_id"], source_ref="steps:audit_trimestrale", decision="confirmed",
        note="Lo fanno davvero ogni trimestre",
    )

    assert result.ok, result.reason
    saved = wd.get_bpmn_model(scope["bpmn_model_id"])["xml"]
    marks = _node_marks(saved)
    assert marks["Audit trimestrale dei fornitori strategici"] == "confirmed"
    assert "Apri richiesta di acquisto (modulo)" in saved, "la modifica a mano deve restare"
    assert all(item.source_ref != "steps:audit_trimestrale" for item in result.provenance.awaiting_confirmation)


@needs_db
def test_rejecting_an_inference_removes_it_from_the_plan_and_the_drawing(
    drafted_process_with_an_inference, monkeypatch
):
    from backend import workspace_database as wd
    from backend.agents.process_snapshot import build_process_snapshot
    from backend.workspace_services import element_review

    scope = drafted_process_with_an_inference
    monkeypatch.setattr(settings, "openai_api_key", None)
    version_before = build_process_snapshot(scope["process_id"]).version

    result = element_review.review_plan_element(
        scope["process_id"], source_ref="steps:audit_trimestrale", decision="rejected",
    )

    assert result.ok, result.reason
    assert result.draft is not None and result.draft.ok
    after = build_process_snapshot(scope["process_id"])
    assert after.version > version_before
    assert all(step["id"] != "audit_trimestrale" for step in after.process_understanding["steps"])
    saved = wd.get_bpmn_model(scope["bpmn_model_id"])["xml"]
    assert "Audit trimestrale" not in saved
    # Il flusso intorno resta intero: la verifica porta ancora all'ordine.
    assert "Crea e invia ordine al fornitore" in saved
    decisions = wd.get_bpmn_review(scope["bpmn_model_id"], include_approved=True)["element_decisions"]
    assert decisions["steps:audit_trimestrale"]["decision"] == "rejected"


@needs_db
def test_an_actor_is_not_rejected_from_the_evidence_panel(drafted_process_with_an_inference):
    from backend.workspace_services import element_review

    scope = drafted_process_with_an_inference

    result = element_review.review_plan_element(
        scope["process_id"], source_ref="actors:acquisti", decision="rejected",
    )

    assert not result.ok
    assert result.reason_code == "not_removable"


@needs_db
def test_an_element_that_is_no_longer_in_the_plan_is_reported_as_such(drafted_process_with_an_inference):
    from backend.workspace_services import element_review

    scope = drafted_process_with_an_inference

    result = element_review.review_plan_element(
        scope["process_id"], source_ref="steps:non_esiste", decision="confirmed",
    )

    assert not result.ok
    assert result.reason_code == "element_not_found"


@needs_db
def test_the_review_endpoint_returns_the_reread_report(drafted_process_with_an_inference):
    from fastapi.testclient import TestClient

    from backend.app import app
    from backend.security import get_current_tenant_id

    scope = drafted_process_with_an_inference
    headers = {"X-DeliR-Tenant-Id": get_current_tenant_id()}
    with TestClient(app) as client:
        before = client.get(f"/v1/workspace/processes/{scope['process_id']}/provenance", headers=headers)
        response = client.post(
            f"/v1/workspace/processes/{scope['process_id']}/provenance/decisions",
            json={"source_ref": "steps:audit_trimestrale", "decision": "confirmed"},
            headers=headers,
        )
        missing = client.post(
            f"/v1/workspace/processes/{uuid.uuid4().hex}/provenance/decisions",
            json={"source_ref": "steps:x", "decision": "confirmed"},
            headers=headers,
        )
        invalid = client.post(
            f"/v1/workspace/processes/{scope['process_id']}/provenance/decisions",
            json={"source_ref": "steps:x", "decision": "maybe"},
            headers=headers,
        )

    assert before.status_code == 200
    audit_before = next(
        item for item in before.json()["elements"] if item["source_ref"] == "steps:audit_trimestrale"
    )
    assert audit_before["mark_status"] == "unverified" and audit_before["removable"] is True

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    audit_after = next(
        item for item in body["provenance"]["elements"] if item["source_ref"] == "steps:audit_trimestrale"
    )
    assert audit_after["consultant_decision"] == "confirmed"
    assert audit_after["mark_status"] == "confirmed"
    assert missing.status_code == 404
    assert invalid.status_code == 422
