"""Il request path con DELIR_AUTH_PROVIDER=supabase, senza rete e senza Supabase.

Il verifier vero (`SupabaseTokenVerifier`) gira con un JWKS servito da una
funzione: si prova la catena intera, dall'header HTTP all'`AuthPrincipal`.
"""

from __future__ import annotations

import json
import time
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from jwt.algorithms import ECAlgorithm

pytestmark = pytest.mark.smoke

SUPABASE_URL = "https://progetto.supabase.co"
SUBJECT = str(uuid.uuid4())
TENANT = "pilot"


@pytest.fixture(scope="module")
def client():
    from backend.app import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def signing_key():
    private = ec.generate_private_key(ec.SECP256R1())
    public = json.loads(ECAlgorithm.to_jwk(private.public_key()))
    public.update({"kid": "kid-1", "alg": "ES256"})
    return private, public


@pytest.fixture()
def jwks_state(signing_key):
    return {"down": False, "keys": [signing_key[1]]}


@pytest.fixture()
def supabase_api(monkeypatch, jwks_state):
    """Autenticazione Supabase accesa, verifier vero con JWKS finto."""
    from backend.auth import supabase_jwt
    from backend.security import set_current_tenant_id
    from backend.settings import settings

    monkeypatch.setattr(settings, "delir_auth_enabled", True)
    monkeypatch.setattr(settings, "delir_auth_provider", "supabase")
    monkeypatch.setattr(settings, "supabase_url", SUPABASE_URL)
    monkeypatch.setattr(settings, "delir_api_token", "token-condiviso-che-non-deve-bastare-000")
    monkeypatch.setattr(settings, "delir_admin_token", "chiave-admin-distinta-0000000000000000")
    monkeypatch.setattr(settings, "delir_allowed_tenant_ids", TENANT)
    monkeypatch.setattr(settings, "delir_default_tenant_id", TENANT)
    monkeypatch.setattr(settings, "delir_egress_allowed_hosts", "progetto.supabase.co")

    def fetch(_url: str) -> dict:
        if jwks_state["down"]:
            raise OSError("supabase giu'")
        return {"keys": jwks_state["keys"]}

    cache = supabase_jwt.JwksCache("jwks", ttl_seconds=600, max_stale_seconds=0, fetch=fetch)
    verifier = supabase_jwt.SupabaseTokenVerifier(
        SUPABASE_URL, audience="authenticated", jwks=cache
    )
    monkeypatch.setattr(supabase_jwt, "get_verifier", lambda: verifier)
    set_current_tenant_id(TENANT)
    yield
    set_current_tenant_id("local")


def _token(private, **overrides) -> str:
    now = int(time.time())
    claims = {
        "iss": f"{SUPABASE_URL}/auth/v1",
        "aud": "authenticated",
        "sub": SUBJECT,
        "role": "authenticated",
        "is_anonymous": False,
        "session_id": "sessione-1",
        "iat": now,
        "exp": now + 1800,
        **overrides,
    }
    return jwt.encode(claims, private, algorithm="ES256", headers={"kid": "kid-1"})


def _headers(token: str, **extra: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-DeliR-Tenant-ID": TENANT, **extra}


def test_a_supabase_session_is_a_person(client, supabase_api, signing_key):
    response = client.get("/v1/auth/me", headers=_headers(_token(signing_key[0])))

    assert response.status_code == 200
    body = response.json()
    assert body["caller_id"] == SUBJECT
    assert body["auth_mode"] == "supabase"
    assert body["has_user_identity"] is True
    assert body["is_admin"] is False


def test_the_user_header_cannot_change_who_you_are(client, supabase_api, signing_key):
    response = client.get(
        "/v1/auth/me",
        headers=_headers(_token(signing_key[0]), **{"X-DeliR-User-Id": "qualcun-altro"}),
    )

    assert response.json()["caller_id"] == SUBJECT


def test_the_shared_token_no_longer_opens_the_door(client, supabase_api):
    from backend.settings import settings

    response = client.get("/v1/auth/me", headers=_headers(settings.delir_api_token))

    assert response.status_code == 401


@pytest.mark.parametrize(
    "overrides",
    [
        {"exp": int(time.time()) - 600},
        {"iss": "https://altro.supabase.co/auth/v1"},
        {"role": "anon"},
        {"is_anonymous": True},
    ],
)
def test_an_invalid_session_is_refused(client, supabase_api, signing_key, overrides):
    response = client.get("/v1/auth/me", headers=_headers(_token(signing_key[0], **overrides)))

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_without_a_token_nothing_is_served(client, supabase_api):
    assert client.get("/v1/auth/me", headers={"X-DeliR-Tenant-ID": TENANT}).status_code == 401


def test_a_valid_session_on_a_tenant_outside_the_allowlist_is_refused(
    client, supabase_api, signing_key
):
    response = client.get(
        "/v1/auth/me",
        headers={**_headers(_token(signing_key[0])), "X-DeliR-Tenant-ID": "altro"},
    )

    assert response.status_code == 403


def test_when_supabase_cannot_be_verified_the_answer_is_503_not_open(
    client, supabase_api, jwks_state, signing_key
):
    jwks_state["down"] = True

    response = client.get("/v1/auth/me", headers=_headers(_token(signing_key[0])))

    assert response.status_code == 503


def test_admin_operations_still_need_the_admin_key(client, supabase_api, signing_key):
    """B1 non introduce ruoli: la chiave admin resta finche' non arriva la membership (B2)."""
    from backend.settings import settings

    token = _token(signing_key[0])
    blocked = client.delete("/v1/consultant-chat/sessions", headers=_headers(token))
    allowed = client.delete(
        "/v1/consultant-chat/sessions",
        headers=_headers(token, **{"X-DeliR-Admin-Token": settings.delir_admin_token}),
    )

    assert blocked.status_code == 403
    assert allowed.status_code == 200


def test_a_websocket_authenticates_with_the_same_session(supabase_api, signing_key):
    import asyncio

    from backend.security import authenticate_websocket

    class FakeSocket:
        def __init__(self, message: str) -> None:
            self.message = message
            self.closed_with: int | None = None

        async def accept(self) -> None:
            return None

        async def receive_text(self) -> str:
            return self.message

        async def close(self, code: int) -> None:
            self.closed_with = code

    def run(token: str) -> tuple:
        socket = FakeSocket(json.dumps({"type": "auth", "tenant_id": TENANT, "api_token": token}))
        principal = asyncio.run(authenticate_websocket(socket))
        return principal, socket.closed_with

    principal, closed = run(_token(signing_key[0]))
    assert principal is not None and principal.user_id == SUBJECT and closed is None

    principal, closed = run(_token(signing_key[0], role="anon"))
    assert principal is None and closed == 1008


def test_the_browser_learns_how_to_log_in_without_credentials(client, supabase_api, monkeypatch):
    from backend.settings import settings

    monkeypatch.setattr(settings, "supabase_publishable_key", "sb_publishable_chiave-del-browser")

    response = client.get("/v1/auth/config")

    assert response.status_code == 200
    assert response.json() == {
        "provider": "supabase",
        "supabase_url": SUPABASE_URL,
        "supabase_publishable_key": "sb_publishable_chiave-del-browser",
    }
    # Niente che il browser non debba vedere.
    assert settings.delir_admin_token not in response.text
    assert settings.delir_api_token not in response.text


@pytest.mark.parametrize(
    ("enabled", "provider", "expected"),
    [(False, "supabase", "local"), (True, "token", "token")],
)
def test_without_supabase_the_config_says_nothing_more(client, monkeypatch, enabled, provider, expected):
    from backend.settings import settings

    monkeypatch.setattr(settings, "delir_auth_enabled", enabled)
    monkeypatch.setattr(settings, "delir_auth_provider", provider)
    monkeypatch.setattr(settings, "supabase_url", SUPABASE_URL)
    monkeypatch.setattr(settings, "supabase_publishable_key", "sb_publishable_x")

    body = client.get("/v1/auth/config").json()

    assert body == {"provider": expected, "supabase_url": "", "supabase_publishable_key": ""}
