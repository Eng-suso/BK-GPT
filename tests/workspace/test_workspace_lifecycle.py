"""Un incarico che finisce esce dal lavoro corrente, non dalla storia.

Il workspace conosceva solo record attivi. Un cliente chiuso restava
nell'elenco insieme a quelli in corso, e l'unico modo di toglierlo era
cancellarlo — cioe' perdere progetti, processi, fonti e decisioni.

Qui si verificano tre proprieta':

1. archiviare chiude anche cio' che sta sotto, e ripristinare riapre solo cio'
   che era stato chiuso in quel momento;
2. gli elenchi operativi mostrano il lavoro corrente, l'archivio il resto, e i
   conteggi che il consulente legge non contano record chiusi;
3. eliminare e' l'unica operazione che perde qualcosa, e dichiara prima cosa
   porta via.
"""

from __future__ import annotations

import uuid

import pytest

from backend.settings import settings


pytestmark = pytest.mark.skipif(
    not settings.workspace_database_url, reason="serve WORKSPACE_DATABASE_URL"
)


@pytest.fixture()
def tenant():
    from backend.security import reset_current_tenant_id, set_current_tenant_id

    token = set_current_tenant_id(f"t-{uuid.uuid4().hex[:8]}")
    try:
        yield
    finally:
        reset_current_tenant_id(token)


@pytest.fixture()
def engagement(tenant):
    """Un cliente con un progetto, un processo, una fonte e una decisione."""
    from backend import workspace_database as wd

    client = wd.create_client(name=f"Esaote {uuid.uuid4().hex[:6]}")
    project = wd.create_project(
        client_id=client["id"],
        name=f"Ciclo ordini {uuid.uuid4().hex[:6]}",
        objective="Ricostruire l'AS-IS del ciclo ordini.",
    )
    process = wd.create_process(project_id=project["id"], name="Gestione richieste")
    source = wd.create_project_source(
        project_id=project["id"],
        process_id=process["id"],
        name="Intervista Laura",
        type="Intervista",
    )
    decision = wd.create_project_decision(
        project_id=project["id"], title="Approvazione a due firme"
    )
    return {
        "client": client,
        "project": project,
        "process": process,
        "source": source,
        "decision": decision,
    }


def test_archiving_a_client_closes_the_work_under_it(engagement):
    from backend import workspace_database as wd

    client_id = engagement["client"]["id"]
    archived = wd.archive_client(client_id, "Incarico concluso a giugno")

    assert archived["archived_at"]
    assert archived["archive_reason"] == "Incarico concluso a giugno"
    assert wd.get_project(engagement["project"]["id"])["archived_at"]
    assert wd.get_process(engagement["process"]["id"])["archived_at"]


def test_the_operational_lists_show_the_work_in_progress(engagement):
    from backend import workspace_database as wd

    wd.archive_client(engagement["client"]["id"])

    assert [c["id"] for c in wd.list_clients()] == []
    assert [p["id"] for p in wd.list_projects()] == []
    assert wd.list_project_processes(engagement["project"]["id"]) == []

    # Chiuso non vuol dire perduto.
    assert engagement["client"]["id"] in {c["id"] for c in wd.list_clients(include_archived=True)}
    archive = wd.list_archive()
    assert engagement["client"]["id"] in {c["id"] for c in archive["clients"]}
    assert engagement["project"]["id"] in {p["id"] for p in archive["projects"]}
    assert engagement["process"]["id"] in {p["id"] for p in archive["processes"]}


def test_restoring_a_client_reopens_what_was_closed_with_it(engagement):
    from backend import workspace_database as wd

    wd.archive_client(engagement["client"]["id"])
    restored = wd.restore_client(engagement["client"]["id"])

    assert restored["archived_at"] is None
    assert restored["projects"] == 1
    assert wd.get_project(engagement["project"]["id"])["archived_at"] is None
    assert wd.get_process(engagement["process"]["id"])["archived_at"] is None


def test_a_process_closed_on_its_own_stays_closed_when_the_client_reopens(engagement):
    from backend import workspace_database as wd

    # Il processo si chiude prima, per conto suo.
    wd.archive_process(engagement["process"]["id"], "Sostituito dal nuovo flusso")
    wd.archive_client(engagement["client"]["id"])
    wd.restore_client(engagement["client"]["id"])

    assert wd.get_project(engagement["project"]["id"])["archived_at"] is None
    # Riaprire il cliente non annulla una decisione presa prima e per altri motivi.
    process = wd.get_process(engagement["process"]["id"])
    assert process["archived_at"]
    assert process["archive_reason"] == "Sostituito dal nuovo flusso"


def test_reopening_a_project_reopens_the_client_it_belongs_to(engagement):
    from backend import workspace_database as wd

    wd.archive_client(engagement["client"]["id"])
    wd.restore_project(engagement["project"]["id"])

    clients = {c["id"]: c for c in wd.list_clients()}
    assert engagement["client"]["id"] in clients


def test_the_project_count_a_consultant_reads_ignores_closed_work(engagement):
    from backend import workspace_database as wd

    before = next(c for c in wd.list_clients() if c["id"] == engagement["client"]["id"])
    assert before["projects"] == 1

    wd.archive_project(engagement["project"]["id"])

    after = next(c for c in wd.list_clients() if c["id"] == engagement["client"]["id"])
    assert after["projects"] == 0
    assert after["processes"] == []
    assert wd.get_project(engagement["project"]["id"])["processes"] == 0


def test_archiving_twice_does_not_move_the_closing_date(engagement):
    from backend import workspace_database as wd

    first = wd.archive_client(engagement["client"]["id"], "Chiuso a giugno")
    second = wd.archive_client(engagement["client"]["id"], "Chiuso a dicembre")

    assert second["archived_at"] == first["archived_at"]
    assert second["archive_reason"] == "Chiuso a giugno"


def test_the_impact_is_counted_before_anything_is_lost(engagement):
    from backend import workspace_database as wd

    impact = wd.client_impact(engagement["client"]["id"])

    assert impact["name"] == engagement["client"]["name"]
    assert impact["projects"] == 1
    assert impact["processes"] == 1
    assert impact["sources"] == 1
    assert impact["decisions"] == 1
    # Il conteggio non ha toccato niente.
    assert wd.get_project(engagement["project"]["id"]) is not None


def test_deleting_a_client_takes_everything_under_it(engagement):
    from backend import workspace_database as wd

    removed = wd.delete_client(engagement["client"]["id"])

    assert removed["projects"] == 1
    assert removed["processes"] == 1
    assert wd.get_project(engagement["project"]["id"]) is None
    assert wd.get_process(engagement["process"]["id"]) is None
    assert wd.list_project_sources(engagement["project"]["id"]) == []
    assert wd.list_project_decisions(engagement["project"]["id"]) == []
    assert wd.get_bpmn_model(engagement["process"]["bpmn_model_id"]) is None


def test_deleting_a_process_leaves_its_project_standing(engagement):
    from backend import workspace_database as wd

    wd.delete_process(engagement["process"]["id"])

    project = wd.get_project(engagement["project"]["id"])
    assert project is not None
    assert project["processes"] == 0
    assert project["process_items"] == []


def test_a_record_that_is_not_there_says_so(tenant):
    from backend import workspace_database as wd

    with pytest.raises(ValueError, match="non trovato"):
        wd.archive_client("cliente-inesistente")
    with pytest.raises(ValueError, match="non trovato"):
        wd.delete_project("progetto-inesistente")
    with pytest.raises(ValueError, match="non trovato"):
        wd.process_impact("processo-inesistente")


# --- superficie HTTP -------------------------------------------------------


@pytest.fixture()
def http():
    from fastapi.testclient import TestClient

    from backend.app import app

    with TestClient(app) as client:
        yield client


def test_the_api_closes_reopens_and_lists_the_archive(http):
    # Creati dallo stesso canale che poi li chiude: il tenant del test e quello
    # della richiesta HTTP non sono lo stesso.
    client = http.post(
        "/v1/workspace/clients", json={"name": f"Esaote {uuid.uuid4().hex[:6]}"}
    ).json()
    http.post(
        "/v1/workspace/projects",
        json={"client_id": client["id"], "name": f"Ciclo ordini {uuid.uuid4().hex[:6]}"},
    )
    client_id = client["id"]

    impact = http.get(f"/v1/workspace/clients/{client_id}/impact")
    assert impact.status_code == 200
    assert impact.json()["projects"] == 1

    archived = http.post(
        f"/v1/workspace/clients/{client_id}/archive", json={"reason": "Incarico concluso"}
    )
    assert archived.status_code == 200
    assert archived.json()["archived_at"]

    listed = http.get("/v1/workspace/clients")
    assert client_id not in {row["id"] for row in listed.json()}

    archive = http.get("/v1/workspace/archive")
    assert archive.status_code == 200
    assert client_id in {row["id"] for row in archive.json()["clients"]}

    restored = http.post(f"/v1/workspace/clients/{client_id}/restore")
    assert restored.status_code == 200
    assert restored.json()["archived_at"] is None
    assert client_id in {row["id"] for row in http.get("/v1/workspace/clients").json()}


def test_the_api_reports_a_missing_record_as_not_found(http):
    response = http.post("/v1/workspace/projects/non-esiste/archive", json={})

    assert response.status_code == 404
