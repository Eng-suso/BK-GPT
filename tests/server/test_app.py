"""
Backend integration tests for the FastAPI application.
Uses TestClient from httpx (FastAPI's recommended test client).

Run with: uv run pytest tests/ -v
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    """
    Create a TestClient instance for the FastAPI app.
    Imports are deferred to avoid loading all backend deps at module level.
    """
    from backend.app import app
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def protected_api(monkeypatch):
    """Enable API protection for tests without relying on process env."""
    from backend.security import set_current_tenant_id
    from backend.settings import settings

    monkeypatch.setattr(settings, "delir_auth_enabled", True)
    monkeypatch.setattr(settings, "delir_api_token", "test-api-token")
    monkeypatch.setattr(settings, "delir_admin_token", "test-admin-token")
    monkeypatch.setattr(settings, "delir_allowed_tenant_ids", "")
    monkeypatch.setattr(settings, "delir_default_tenant_id", "local")
    set_current_tenant_id("local")

    yield

    set_current_tenant_id("local")


def auth_headers(tenant_id: str = "tenant-a") -> dict[str, str]:
    return {
        "Authorization": "Bearer test-api-token",
        "X-DeliR-Tenant-ID": tenant_id,
    }


def test_health_check(client: TestClient):
    """The app should respond to GET / or at minimum not crash on startup."""
    # Try the root endpoint; it may 404 or 200 depending on your router setup
    response = client.get("/")
    assert response.status_code in (200, 404, 307)  # All acceptable for root


def test_api_docs_available(client: TestClient):
    """OpenAPI docs should be accessible in development mode."""
    response = client.get("/docs")
    assert response.status_code == 200


def test_openapi_schema(client: TestClient):
    """The OpenAPI JSON schema should be valid and accessible."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    data = response.json()
    assert "openapi" in data
    assert "paths" in data


def test_list_chat_sessions_endpoint(client: TestClient):
    """GET /v1/consultant-chat/sessions should return a list (possibly empty)."""
    response = client.get("/v1/consultant-chat/sessions")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_cors_headers_present(client: TestClient):
    """CORS middleware should return appropriate headers for cross-origin requests."""
    response = client.get(
        "/openapi.json",
        headers={"Origin": "http://localhost:3030"},
    )
    assert response.status_code == 200
    # CORS allow-origin header should be set
    assert "access-control-allow-origin" in response.headers


def test_api_error_envelope_and_request_id_header(client: TestClient):
    """API errors should expose a stable envelope and request id."""
    response = client.get(
        "/v1/consultant-chat/sessions/missing-thread",
        headers={"X-Request-ID": "test-request-id"},
    )

    assert response.status_code == 404
    assert response.headers["x-request-id"] == "test-request-id"

    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "not_found"
    assert payload["error"]["request_id"] == "test-request-id"
    assert payload["meta"]["request_id"] == "test-request-id"


def test_protected_routes_require_bearer_token_when_enabled(
    client: TestClient,
    protected_api,
):
    response = client.get("/v1/consultant-chat/sessions")
    assert response.status_code == 401

    wrong_token = client.get(
        "/v1/consultant-chat/sessions",
        headers={
            "Authorization": "Bearer wrong-token",
            "X-DeliR-Tenant-ID": "tenant-a",
        },
    )
    assert wrong_token.status_code == 401


def test_tenant_header_scopes_chat_sessions(client: TestClient, protected_api):
    created = client.post(
        "/v1/consultant-chat/sessions",
        headers=auth_headers("tenant-a"),
        json={"model_name": "gpt-test", "title": "Tenant A session"},
    )
    assert created.status_code == 200
    thread_id = created.json()["thread_id"]

    tenant_a = client.get(
        "/v1/consultant-chat/sessions",
        headers=auth_headers("tenant-a"),
    )
    assert tenant_a.status_code == 200
    assert any(session["thread_id"] == thread_id for session in tenant_a.json())

    tenant_b = client.get(
        "/v1/consultant-chat/sessions",
        headers=auth_headers("tenant-b"),
    )
    assert tenant_b.status_code == 200
    assert all(session["thread_id"] != thread_id for session in tenant_b.json())


def test_destructive_chat_delete_requires_admin_token(
    client: TestClient,
    protected_api,
):
    created = client.post(
        "/v1/consultant-chat/sessions",
        headers=auth_headers("tenant-admin"),
        json={"model_name": "gpt-test", "title": "Delete guard"},
    )
    assert created.status_code == 200
    thread_id = created.json()["thread_id"]

    blocked = client.delete(
        f"/v1/consultant-chat/sessions/{thread_id}",
        headers=auth_headers("tenant-admin"),
    )
    assert blocked.status_code == 403

    deleted = client.delete(
        f"/v1/consultant-chat/sessions/{thread_id}",
        headers={
            **auth_headers("tenant-admin"),
            "X-DeliR-Admin-Token": "test-admin-token",
        },
    )
    assert deleted.status_code == 200
