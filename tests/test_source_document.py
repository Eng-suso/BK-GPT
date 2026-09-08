"""Una fonte si apre e si legge, non si riassume in due righe.

Il pannello Fonti mostrava per ogni fonte il solo campo `meta`, troncato a 240
caratteri quando l'evidenza arrivava dalla chat. Per verificare un'affermazione
serve il testo originale: chi apre "Intervista Laura Conti" vuole l'intervista.

Il testo c'era gia' - lo tiene la memoria episodica - ma non era raggiungibile
dal record della fonte. Qui si verifica il ponte, dal salvataggio in chat fino
alla risposta HTTP.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from backend.settings import settings

if not settings.workspace_database_url:
    pytest.skip("serve WORKSPACE_DATABASE_URL", allow_module_level=True)

FIXTURES = Path(__file__).parent / "fixtures" / "interviews"
INTERVIEW = "a2_paolo_marchetti_manutenzione.md"
TITLE = "Intervista Paolo Marchetti - Manutenzione"
SUMMARY = "Come nascono e come si chiudono le richieste urgenti in Manutenzione."


@pytest.fixture()
def saved_interview():
    """Un'intervista salvata come la salva l'agente, in un processo suo."""
    from backend import workspace_database as wd
    from backend.agents.scope_guard import bind_active_scope
    from backend.memory.episodic import episodic_store
    from backend.schemas.chat import ProcessChatScope
    from backend.security import reset_current_tenant_id, set_current_tenant_id
    from backend.toolsets.process_memory import manage_process_evidence
    from sqlalchemy import text

    tenant = f"t-{uuid.uuid4().hex[:8]}"
    token = set_current_tenant_id(tenant)
    suffix = uuid.uuid4().hex[:8]
    client = wd.create_client(name=f"Contoso {suffix}")
    project = wd.create_project(client_id=client["id"], name=f"Acquisti {suffix}")
    process = wd.create_process(project_id=project["id"], name="Acquisti indiretti")

    raw = (FIXTURES / INTERVIEW).read_text(encoding="utf-8")
    with bind_active_scope(
        ProcessChatScope(
            type="process", project_id=project["id"], process_id=process["id"]
        )
    ):
        manage_process_evidence.invoke(
            {
                "operation": "save_interview",
                "project_id": project["id"],
                "process_id": process["id"],
                "title": TITLE,
                "raw_content": raw,
                "summary": SUMMARY,
                "participants": ["Paolo Marchetti"],
            }
        )

    source = next(
        item
        for item in wd.list_project_sources(project["id"])
        if item["name"] == TITLE
    )
    try:
        yield {
            "tenant": tenant,
            "project": project["id"],
            "process": process["id"],
            "source": source,
            "raw": raw,
        }
    finally:
        with episodic_store.episodic_connection() as session:
            session.execute(
                text("DELETE FROM episodes WHERE project = :p"), {"p": project["id"]}
            )
        reset_current_tenant_id(token)


def test_the_source_carries_its_full_text_not_a_truncated_note(saved_interview):
    from backend.workspace_services.source_document import source_document

    document = source_document(saved_interview["source"]["id"])

    assert document is not None
    assert document["has_content"]
    # Il testo integrale, non l'estratto: la nota della fonte si ferma a 240
    # caratteri, l'intervista e' lunga migliaia.
    assert len(document["content"]) > len(saved_interview["source"]["meta"]) * 5
    assert "Le urgenze sono un capitolo a parte." in document["content"]


def test_the_source_carries_its_summary_and_who_was_present(saved_interview):
    from backend.workspace_services.source_document import source_document

    document = source_document(saved_interview["source"]["id"])

    assert document["summary"] == SUMMARY
    assert document["participants"] == ["Paolo Marchetti"]
    assert document["episode_id"]


def test_the_source_stays_linked_to_its_process(saved_interview):
    from backend.workspace_services.source_document import source_document

    document = source_document(saved_interview["source"]["id"])

    assert document["process_id"] == saved_interview["process"]
    assert document["project_id"] == saved_interview["project"]


def test_a_source_without_a_transcript_still_opens(saved_interview):
    """Un documento registrato a mano non ha testo grezzo: la fonte resta
    apribile e lo dichiara, invece di mostrare una sezione vuota."""
    from backend import workspace_database as wd
    from backend.workspace_services.source_document import source_document

    source, _created = wd.ensure_project_source(
        project_id=saved_interview["project"],
        process_id=saved_interview["process"],
        name="Procedura interna acquisti",
        type="Documento",
        meta="Procedura ricevuta dal cliente.",
    )
    document = source_document(source["id"])

    assert document is not None
    assert not document["has_content"]
    assert document["content"] == ""
    assert document["summary"] == "Procedura ricevuta dal cliente."


def test_an_unknown_source_is_not_found():
    from backend.workspace_services.source_document import source_document

    assert source_document("source-che-non-esiste") is None


def test_the_endpoint_returns_the_document(saved_interview):
    from fastapi.testclient import TestClient

    from backend.app import app

    # Il tenant di una richiesta HTTP arriva dall'header, non dal contesto del
    # test: senza, la fonte e' di un altro inquilino e non esiste.
    with TestClient(app) as client:
        response = client.get(
            f"/v1/workspace/sources/{saved_interview['source']['id']}/document",
            headers={"X-Delir-Tenant-Id": saved_interview["tenant"]},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == TITLE
    assert body["has_content"]
    assert "Le urgenze sono un capitolo a parte." in body["content"]


def test_the_endpoint_is_404_for_an_unknown_source():
    from fastapi.testclient import TestClient

    from backend.app import app

    with TestClient(app) as client:
        response = client.get("/v1/workspace/sources/non-esiste/document")

    assert response.status_code == 404
