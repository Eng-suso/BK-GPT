"""Il prodotto dice chi sta usando cosa, per quanto lo sappia davvero.

La barra in alto mostrava "Marco Bianchi" e "Gruppo DeliR" scritti nel codice:
davanti a un cliente sono la prima cosa che si legge, e dicevano una cosa falsa.
Il backend oggi non conosce persone - conosce lo spazio di lavoro e come la
richiesta e' stata autenticata - e questi test fissano che sia esattamente
quello a uscire, dichiarando cio' che manca invece di riempirlo.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.settings import settings


ME = "/v1/auth/me"


@pytest.fixture()
def client():
    from backend.app import app

    with TestClient(app) as test_client:
        yield test_client


def test_without_authentication_it_says_so_instead_of_naming_someone(client):
    body = client.get(ME).json()

    assert body["auth_enabled"] is False
    assert body["auth_mode"] == "local"
    # La cosa piu' importante per un pilot: il prodotto dichiara di non sapere
    # chi sei, invece di mostrare un nome inventato.
    assert body["has_user_identity"] is False
    assert body["tenant_id"]


def test_with_authentication_it_reports_the_workspace_of_the_request(client, monkeypatch):
    from backend.security import set_current_tenant_id

    monkeypatch.setattr(settings, "delir_auth_enabled", True)
    monkeypatch.setattr(settings, "delir_api_token", "test-api-token")
    monkeypatch.setattr(settings, "delir_admin_token", "test-admin-token")
    monkeypatch.setattr(settings, "delir_allowed_tenant_ids", "")
    monkeypatch.setattr(settings, "delir_default_tenant_id", "local")

    try:
        response = client.get(
            ME,
            headers={
                "Authorization": "Bearer test-api-token",
                "X-DeliR-Tenant-ID": "studio-frascheri",
            },
        )
    finally:
        set_current_tenant_id("local")

    body = response.json()
    assert response.status_code == 200
    assert body["tenant_id"] == "studio-frascheri"
    assert body["auth_mode"] == "bearer"
    assert body["auth_enabled"] is True
    # Con un token di amministrazione configurato, una chiamata col token
    # normale non e' amministratore.
    assert body["is_admin"] is False
    assert body["has_user_identity"] is False


def test_a_workspace_outside_the_allowlist_is_refused(client, monkeypatch):
    from backend.security import set_current_tenant_id

    monkeypatch.setattr(settings, "delir_auth_enabled", True)
    monkeypatch.setattr(settings, "delir_api_token", "test-api-token")
    monkeypatch.setattr(settings, "delir_allowed_tenant_ids", "studio-frascheri")

    try:
        response = client.get(
            ME,
            headers={
                "Authorization": "Bearer test-api-token",
                "X-DeliR-Tenant-ID": "studio-estraneo",
            },
        )
    finally:
        set_current_tenant_id("local")

    # Lo spazio di lavoro arriva da un header che il client imposta: se
    # l'ambiente ne dichiara uno solo, chiederne un altro non deve restituire
    # nemmeno il nome di quello richiesto.
    assert response.status_code == 403
    assert "tenant_id" not in response.text


def test_identity_requires_credentials_when_authentication_is_on(client, monkeypatch):
    from backend.security import set_current_tenant_id

    monkeypatch.setattr(settings, "delir_auth_enabled", True)
    monkeypatch.setattr(settings, "delir_api_token", "test-api-token")
    monkeypatch.setattr(settings, "delir_allowed_tenant_ids", "")

    try:
        response = client.get(ME)
    finally:
        set_current_tenant_id("local")

    # L'endpoint racconta la configurazione dell'accesso: non puo' essere
    # l'unico aperto a chi non ha credenziali.
    assert response.status_code == 401
