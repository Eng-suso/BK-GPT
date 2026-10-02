"""WS-04: un incarico ha un referente e una finestra temporale.

Il progetto sapeva in che fase era e quanto era avanti, ma non chi lo segue ne'
fra quali date sta. Il "referente" mostrato nell'elenco era preso in prestito
dall'owner del primo processo registrato: un progetto senza processi non aveva
referente, e uno con tre ne mostrava uno a caso.

Le date sono il punto delicato. Arrivano da due parti - il form del consulente e
il modello, che propone quello che ha sentito in chat - e nessuna delle due e'
affidabile: il confine Pydantic e' l'unico posto in cui "prossimo mese" viene
fermato prima di diventare il contenuto di una colonna.
"""

from __future__ import annotations

import json
import uuid

import pytest
from pydantic import ValidationError

from backend.schemas.workspace import CreateProjectRequest, UpdateProjectRequest
from backend.settings import settings
from backend.toolsets.workspace import ProjectUpdateInput


# --- il confine: senza database --------------------------------------------

def test_an_iso_date_is_normalized_at_the_boundary():
    request = UpdateProjectRequest(start_date=" 2026-09-01 ", end_date="2026-12-15")

    assert request.start_date == "2026-09-01"
    assert request.end_date == "2026-12-15"


def test_a_date_that_is_not_a_date_is_refused_before_it_reaches_a_column():
    for payload in ({"start_date": "prossimo mese"}, {"end_date": "15/12/2026"}):
        with pytest.raises(ValidationError, match="Data non valida"):
            UpdateProjectRequest(**payload)


def test_the_three_intentions_stay_distinct():
    """`None` non tocca, `""` cancella, una data registra."""
    assert UpdateProjectRequest().start_date is None
    assert UpdateProjectRequest(start_date="").start_date == ""
    assert UpdateProjectRequest(start_date="2026-09-01").start_date == "2026-09-01"


def test_the_model_gets_the_same_boundary_as_the_form():
    """Una data proposta dall'LLM non e' piu' affidabile di una del client."""
    assert ProjectUpdateInput(project_id="p", start_date="2026-09-01").start_date == "2026-09-01"

    with pytest.raises(ValidationError, match="Data non valida"):
        ProjectUpdateInput(project_id="p", end_date="quando finiamo")


def test_creating_a_project_accepts_the_window_and_the_lead():
    request = CreateProjectRequest(
        client_id="esaote",
        name="Mappatura acquisti",
        lead="Laura Verdi",
        start_date="2026-09-01",
    )

    assert request.lead == "Laura Verdi"
    assert request.start_date == "2026-09-01"
    assert request.end_date is None


# --- il record: serve il database operativo --------------------------------

pytestmark_db = pytest.mark.skipif(
    not settings.workspace_database_url, reason="serve WORKSPACE_DATABASE_URL"
)


@pytest.fixture()
def tenant():
    """Isola il test in un tenant proprio."""
    from backend.security import reset_current_tenant_id, set_current_tenant_id

    token = set_current_tenant_id(f"t-{uuid.uuid4().hex[:8]}")
    try:
        yield
    finally:
        reset_current_tenant_id(token)


@pytest.fixture()
def project(tenant):
    from backend import workspace_database as wd

    client = wd.create_client(name=f"Esaote {uuid.uuid4().hex[:6]}")
    return wd.create_project(
        client_id=client["id"],
        name=f"Acquisti {uuid.uuid4().hex[:6]}",
        lead="Laura Verdi",
        start_date="2026-09-01",
        end_date="2026-12-15",
    )


@pytestmark_db
def test_the_project_record_keeps_the_lead_and_the_window(project):
    from backend import workspace_database as wd

    stored = wd.get_project(project["id"])

    assert stored["lead"] == "Laura Verdi"
    assert stored["start_date"] == "2026-09-01"
    assert stored["end_date"] == "2026-12-15"


@pytestmark_db
def test_a_project_declared_without_them_leaves_them_unset(tenant):
    """Non dichiarato non e' un placeholder: e' assente, e si vede."""
    from backend import workspace_database as wd

    client = wd.create_client(name=f"Esaote {uuid.uuid4().hex[:6]}")
    created = wd.create_project(client_id=client["id"], name="Senza date")

    assert created["lead"] is None
    assert created["start_date"] is None
    assert created["end_date"] is None


@pytestmark_db
def test_an_emptied_field_is_forgotten_and_an_undeclared_one_is_kept(project):
    from backend import workspace_database as wd

    updated = wd.update_project(project["id"], start_date="", lead="Marco Bianchi")

    assert updated["start_date"] is None
    assert updated["lead"] == "Marco Bianchi"
    # `end_date` non e' stato dichiarato: resta com'era.
    assert updated["end_date"] == "2026-12-15"


@pytest.fixture()
def http_project():
    """Un progetto creato via HTTP, quindi nel tenant che la richiesta stabilisce.

    Il record va creato dalla stessa parte da cui lo si legge: il tenant arriva
    dal middleware, e un progetto nato in un tenant di test sarebbe invisibile
    alla richiesta che poi lo modifica.
    """
    from fastapi.testclient import TestClient

    from backend.app import app

    with TestClient(app) as http:
        client = http.post(
            "/v1/workspace/clients", json={"name": f"Esaote {uuid.uuid4().hex[:6]}"}
        ).json()
        project = http.post(
            "/v1/workspace/projects",
            json={
                "client_id": client["id"],
                "name": f"Acquisti {uuid.uuid4().hex[:6]}",
                "lead": "Laura Verdi",
                "start_date": "2026-09-01",
                "end_date": "2026-12-15",
            },
        ).json()
        yield http, project


@pytestmark_db
def test_the_window_survives_the_round_trip_over_http(http_project):
    http, project = http_project

    assert project["lead"] == "Laura Verdi"
    assert project["start_date"] == "2026-09-01"

    response = http.patch(
        f"/v1/workspace/projects/{project['id']}",
        json={"lead": "Marco Bianchi", "end_date": "2027-01-31"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["lead"] == "Marco Bianchi"
    assert body["end_date"] == "2027-01-31"
    # Non dichiarata, quindi intatta.
    assert body["start_date"] == "2026-09-01"


@pytestmark_db
def test_an_unreadable_date_is_refused_over_http(http_project):
    http, project = http_project

    response = http.patch(
        f"/v1/workspace/projects/{project['id']}",
        json={"start_date": "prossimo mese"},
    )

    assert response.status_code == 422, response.text


@pytestmark_db
def test_the_project_chat_can_record_what_the_consultant_said(project):
    """Detto in chat e non scritto, domani non c'e' piu' (lezione PROJECT-01)."""
    from backend.toolsets.workspace import update_workspace_project

    result = json.loads(
        update_workspace_project.invoke(
            {
                "project_id": project["id"],
                "lead": "Giulia Rossi",
                "start_date": "2026-10-01",
            }
        ).split("\n", 1)[1]
    )

    assert result["payload"]["lead"] == "Giulia Rossi"
    assert result["payload"]["start_date"] == "2026-10-01"
