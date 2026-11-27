"""Lo spazio di lavoro di un account: chi lo assegna, e cosa ne discende.

Un account personale (`acct-<sub>`) lo assegna solo il server, dal token
verificato. Da lui discende il consulente canonical, cioe' la memoria.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from backend import security
from backend.settings import settings

pytestmark = pytest.mark.smoke


def test_an_account_has_its_own_consultant():
    person = str(uuid.uuid4())

    tenant = security.account_tenant_id(person)

    assert tenant == f"acct-{person}"
    assert security.consultant_id_for_tenant(tenant) == person
    assert security.tenant_id_for_consultant(person) == tenant


@pytest.mark.parametrize("tenant", ["local", "pilot", None])
def test_a_shared_space_keeps_the_default_consultant(tenant):
    """Il pilota col token condiviso non perde la memoria gia' salvata."""
    assert security.consultant_id_for_tenant(tenant) == str(settings.default_consultant_id)
    assert security.tenant_id_for_consultant(str(settings.default_consultant_id)) is None


def test_the_current_consultant_follows_the_current_space():
    person = str(uuid.uuid4())
    token = security.set_current_tenant_id(security.account_tenant_id(person))
    try:
        assert security.get_current_consultant_id() == person
    finally:
        security.reset_current_tenant_id(token)

    assert security.get_current_consultant_id() == str(settings.default_consultant_id)


def test_no_client_can_ask_for_an_account_space(monkeypatch):
    """Col token condiviso, un header `acct-<qualcuno>` aprirebbe la sua memoria."""
    monkeypatch.setattr(settings, "delir_allowed_tenant_ids", "")

    with pytest.raises(HTTPException) as refused:
        security.requested_tenant_id(f"acct-{uuid.uuid4()}")

    assert refused.value.status_code == 403
    assert security.requested_tenant_id("pilot") == "pilot"


def test_the_account_header_is_refused_over_http(monkeypatch):
    from fastapi.testclient import TestClient

    from backend.app import app

    monkeypatch.setattr(settings, "delir_allowed_tenant_ids", "")
    with TestClient(app) as client:
        response = client.get(
            "/v1/auth/me", headers={"X-DeliR-Tenant-ID": f"acct-{uuid.uuid4()}"}
        )

    assert response.status_code == 403
