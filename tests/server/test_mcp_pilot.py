"""The personal HTTP bridge must fail closed before reaching MCP tools."""

import asyncio

import httpx
import pytest

from backend.mcp_pilot import create_app


def _get(app, headers: dict[str, str] | None = None) -> httpx.Response:
    async def run() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8765") as client:
            return await client.get("/mcp", headers=headers)

    return asyncio.run(run())


def test_pilot_refuses_requests_without_configured_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DELIR_MCP_PILOT_TOKEN", raising=False)
    response = _get(create_app())
    assert response.status_code == 503


def test_pilot_refuses_missing_or_wrong_bearer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DELIR_MCP_PILOT_TOKEN", "a" * 48)
    app = create_app()
    assert _get(app).status_code == 401
    assert _get(app, {"Authorization": f"Bearer {'b' * 48}"}).status_code == 401


def test_pilot_rejects_malformed_public_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DELIR_MCP_PILOT_PUBLIC_HOST", "example.com/path")
    with pytest.raises(ValueError, match="hostname pubblico"):
        create_app()
