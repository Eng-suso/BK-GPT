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
