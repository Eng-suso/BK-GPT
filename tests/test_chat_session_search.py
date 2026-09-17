"""Ritrovare una conversazione, non scorrerle tutte.

Il bottone della ricerca nella cronologia mostrava un avviso e basta. Qui la
ricerca esiste davvero, e questi test fissano cosa deve saper fare per essere
utile a un consulente che ha venti chat sullo stesso cliente: trovare per
parole del testo scambiato (non solo per titolo), restare dentro il tenant e
dentro la superficie da cui e' partita, e restituire il pezzo di frase che dice
quale conversazione riaprire.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from backend.settings import settings


_needs_db = pytest.mark.skipif(
    not settings.workspace_database_url, reason="serve WORKSPACE_DATABASE_URL"
)

SEARCH = "/v1/consultant-chat/sessions/search"


@pytest.fixture()
def client():
    from backend.app import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def conversations():
    """Due conversazioni con testo diverso, rimosse a fine test.

    Le sessioni vivono in un database condiviso con il resto della suite: i
    testi portano un marcatore unico, cosi' le asserzioni non dipendono da cosa
    altro c'e' dentro.
    """
    from backend import database

    marker = uuid.uuid4().hex[:10]
    threads = {
        "acquisti": str(uuid.uuid4()),
        "magazzino": str(uuid.uuid4()),
    }

    database.create_chat_session(
        thread_id=threads["acquisti"],
        model_name="gpt-test",
        title=f"Ciclo passivo {marker}",
        scope_type="process",
        scope_key=f"process:{marker}",
    )
    database.append_chat_message(
        threads["acquisti"],
        "user",
        f"Chi firma l'ordine al fornitore quando l'importo supera i diecimila euro? [{marker}]",
        scope_key=f"process:{marker}",
    )
    database.append_chat_message(
        threads["acquisti"],
        "assistant",
        f"Le note dicono che l'ordine lo autorizza il responsabile acquisti. [{marker}]",
        scope_key=f"process:{marker}",
    )

    database.create_chat_session(
        thread_id=threads["magazzino"],
        model_name="gpt-test",
        title=f"Accettazione merce {marker}",
        scope_type="consultant",
        scope_key=f"consultant:{marker}",
    )
    database.append_chat_message(
        threads["magazzino"],
        "user",
        f"Il magazzino controlla la merce prima della registrazione? [{marker}]",
        scope_key=f"consultant:{marker}",
    )

    yield {"marker": marker, "threads": threads}

    for thread_id in threads.values():
        database.delete_chat_session(thread_id)


@_needs_db
def test_search_finds_a_conversation_by_what_was_said_in_it(client, conversations):
    marker = conversations["marker"]

    response = client.get(SEARCH, params={"q": f"ordine fornitore {marker}"})

    assert response.status_code == 200
    hits = response.json()
    assert [hit["thread_id"] for hit in hits] == [conversations["threads"]["acquisti"]]

    # Le parole non sono contigue nel messaggio ("l'ordine al fornitore"): una
    # sottostringa secca non lo troverebbe, ed e' esattamente come si cerca.
    hit = hits[0]
    assert "ordine" in hit["snippet"].lower()
    assert hit["snippet_role"] == "user"
    assert hit["match_count"] >= 1


@_needs_db
def test_search_finds_a_conversation_by_title(client, conversations):
    marker = conversations["marker"]

    hits = client.get(SEARCH, params={"q": f"accettazione {marker}"}).json()

    assert [hit["thread_id"] for hit in hits] == [conversations["threads"]["magazzino"]]


@_needs_db
def test_search_stays_inside_the_surface_it_was_started_from(client, conversations):
    marker = conversations["marker"]

    hits = client.get(
        SEARCH, params={"q": marker, "scope_key": f"process:{marker}"}
    ).json()

    # Entrambe le conversazioni contengono il marcatore: quella dell'altro scope
    # non deve comparire, altrimenti cercando dentro un processo si riaprono le
    # chat di un altro.
    assert [hit["thread_id"] for hit in hits] == [conversations["threads"]["acquisti"]]


@_needs_db
def test_empty_query_returns_nothing_rather_than_everything(client, conversations):
    assert client.get(SEARCH, params={"q": "   "}).json() == []


@_needs_db
def test_wildcards_are_searched_literally(client, conversations):
    marker = conversations["marker"]

    # `%` in LIKE significa "qualunque cosa": se non viene reso letterale, questa
    # ricerca restituisce l'intera cronologia invece di zero risultati.
    hits = client.get(SEARCH, params={"q": f"%{marker}"}).json()

    assert hits == []


@_needs_db
def test_search_does_not_cross_tenants(client, conversations, protected_api):
    marker = conversations["marker"]

    other_tenant = client.get(
        SEARCH,
        params={"q": marker},
        headers={
            "Authorization": "Bearer test-api-token",
            "X-DeliR-Tenant-ID": "tenant-estraneo",
        },
    )

    assert other_tenant.status_code == 200
    assert other_tenant.json() == []


@pytest.fixture()
def protected_api(monkeypatch):
    """Autenticazione accesa, cosi' il tenant arriva dall'header."""
    from backend.security import set_current_tenant_id

    monkeypatch.setattr(settings, "delir_auth_enabled", True)
    monkeypatch.setattr(settings, "delir_api_token", "test-api-token")
    monkeypatch.setattr(settings, "delir_admin_token", "test-admin-token")
    monkeypatch.setattr(settings, "delir_allowed_tenant_ids", "")
    monkeypatch.setattr(settings, "delir_default_tenant_id", "local")
    set_current_tenant_id("local")

    yield

    set_current_tenant_id("local")
