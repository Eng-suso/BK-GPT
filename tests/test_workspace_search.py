"""La lente nella barra in alto cerca davvero, in tutto il workspace.

Il campo non aveva un flusso: si scriveva e non succedeva niente. Questi test
fissano cosa deve saper trovare per essere utile a un consulente con venti
incarichi aperti - il cliente, il progetto, il processo, la fonte, senza
ricordarsi sotto quale cliente stiano - e cosa non deve restituire mai: il
lavoro archiviato e quello di un altro tenant.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from backend.settings import settings


_needs_db = pytest.mark.skipif(
    not settings.workspace_database_url, reason="serve WORKSPACE_DATABASE_URL"
)

SEARCH = "/v1/workspace/search"


@pytest.fixture()
def client():
    from backend.app import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def engagement(client):
    """Un cliente con progetto, processo e fonte; rimosso a fine test."""
    from backend import workspace_database

    marker = uuid.uuid4().hex[:8]
    created_client = client.post(
        "/v1/workspace/clients", json={"name": f"Esaote {marker}"}
    ).json()
    project = client.post(
        "/v1/workspace/projects",
        json={
            "client_id": created_client["id"],
            "name": f"Riorganizzazione acquisti {marker}",
            "objective": f"Ridurre i tempi del ciclo passivo {marker}",
        },
    ).json()
    process = client.post(
        f"/v1/workspace/projects/{project['id']}/processes",
        json={"name": f"Ciclo passivo {marker}"},
    ).json()
    source = client.post(
        f"/v1/workspace/projects/{project['id']}/sources",
        json={
            "name": f"Intervista Neri {marker}",
            "type": "Intervista",
            "process_id": process["id"],
        },
    ).json()

    yield {
        "marker": marker,
        "client": created_client,
        "project": project,
        "process": process,
        "source": source,
    }

    workspace_database.delete_client(created_client["id"])


def _hits(response) -> list[dict]:
    assert response.status_code == 200
    return response.json()


@_needs_db
def test_search_reaches_every_kind_of_record(client, engagement):
    marker = engagement["marker"]

    by_kind = {hit["kind"]: hit for hit in _hits(client.get(SEARCH, params={"q": marker}))}

    assert by_kind["client"]["id"] == engagement["client"]["id"]
    assert by_kind["project"]["id"] == engagement["project"]["id"]
    assert by_kind["process"]["id"] == engagement["process"]["id"]
    assert by_kind["source"]["id"] == engagement["source"]["id"]


@_needs_db
def test_a_result_says_where_it_lives(client, engagement):
    marker = engagement["marker"]

    hits = _hits(client.get(SEARCH, params={"q": f"intervista {marker}"}))

    source = next(hit for hit in hits if hit["kind"] == "source")
    # Senza il percorso, "Intervista Neri" non dice sotto quale cliente aprirla.
    assert engagement["client"]["name"] in source["context"]
    assert source["project_id"] == engagement["project"]["id"]
    assert source["process_id"] == engagement["process"]["id"]
    assert source["source_type"] == "Intervista"


@_needs_db
def test_all_the_words_must_match_the_same_record(client, engagement):
    marker = engagement["marker"]

    hits = _hits(client.get(SEARCH, params={"q": f"ciclo passivo {marker}"}))

    # "ciclo passivo" trova il processo e l'obiettivo del progetto che lo cita,
    # non ogni record che nomina un ciclo qualunque.
    found = {hit["kind"] for hit in hits}
    assert "process" in found
    assert all(marker in hit["title"] or marker in hit["context"] for hit in hits)


@_needs_db
def test_the_closest_name_comes_first(client, engagement):
    marker = engagement["marker"]

    hits = _hits(client.get(SEARCH, params={"q": f"esaote {marker}"}))

    # Chi scrive il nome del cliente vuole il cliente, non la ventesima fonte
    # che lo nomina nel percorso.
    assert hits[0]["kind"] == "client"


@_needs_db
def test_the_exact_name_survives_the_cut(client, engagement):
    from backend.workspace_services.global_search import search_workspace

    marker = engagement["marker"]
    exact = f"Ordini {marker}"
    for name in (f"Ordini fornitori {marker}", exact, f"Ordini urgenti {marker}"):
        created = client.post(
            f"/v1/workspace/projects/{engagement['project']['id']}/processes",
            json={"name": name},
        )
        assert created.status_code == 200

    # Con un solo candidato per tipo: l'ordine di pertinenza deve stare nella
    # query, non dopo. Ordinando per nome il processo che si chiama esattamente
    # come la ricerca resterebbe fuori dal taglio.
    hits = search_workspace(exact, per_kind_limit=1)

    assert [hit["title"] for hit in hits if hit["kind"] == "process"] == [exact]


@_needs_db
def test_a_word_in_the_middle_of_a_name_still_ranks_first(client, engagement):
    from backend.workspace_services.global_search import search_workspace

    marker = engagement["marker"]
    for name in (f"Anagrafica fornitori {marker}", f"Ciclo passivo {marker}"):
        created = client.post(
            f"/v1/workspace/projects/{engagement['project']['id']}/processes",
            json={"name": name},
        )
        assert created.status_code == 200

    # "passivo" apre la seconda parola, non il titolo: la regola in SQL deve
    # essere la stessa di quella in Python, altrimenti il candidato giusto viene
    # tagliato prima ancora di essere ordinato.
    hits = search_workspace(f"passivo {marker}", per_kind_limit=1)

    assert [hit["title"] for hit in hits if hit["kind"] == "process"] == [
        f"Ciclo passivo {marker}"
    ]


@_needs_db
def test_archived_work_never_comes_back_from_a_search(client, engagement):
    marker = engagement["marker"]
    archived = client.post(
        f"/v1/workspace/projects/{engagement['project']['id']}/archive",
        json={"reason": "incarico chiuso"},
    )
    assert archived.status_code == 200

    kinds = {hit["kind"] for hit in _hits(client.get(SEARCH, params={"q": marker}))}

    # Il cliente resta: e' il progetto ad essere chiuso, con cio' che sta sotto.
    assert kinds == {"client"}


@_needs_db
def test_empty_query_returns_nothing_rather_than_the_workspace(client, engagement):
    assert _hits(client.get(SEARCH, params={"q": "   "})) == []


@_needs_db
def test_wildcards_are_searched_literally(client, engagement):
    marker = engagement["marker"]

    # Senza escape, `%` significa "qualunque cosa" e la ricerca restituirebbe
    # l'intero workspace.
    assert _hits(client.get(SEARCH, params={"q": f"%{marker}"})) == []


@_needs_db
def test_search_does_not_cross_tenants(client, engagement, monkeypatch):
    from backend.security import set_current_tenant_id

    monkeypatch.setattr(settings, "delir_auth_enabled", True)
    monkeypatch.setattr(settings, "delir_api_token", "test-api-token")
    monkeypatch.setattr(settings, "delir_admin_token", "test-admin-token")
    monkeypatch.setattr(settings, "delir_allowed_tenant_ids", "")
    monkeypatch.setattr(settings, "delir_default_tenant_id", "local")

    try:
        response = client.get(
            SEARCH,
            params={"q": engagement["marker"]},
            headers={
                "Authorization": "Bearer test-api-token",
                "X-DeliR-Tenant-ID": "tenant-estraneo",
            },
        )
    finally:
        set_current_tenant_id("local")

    assert _hits(response) == []
