"""MCP boundary checks without a live workspace or customer data."""

import asyncio

import httpx
import pytest
from mcp import Client

from backend import mcp_server


BPMN = (
    '<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL">'
    '<process id="P"><startEvent id="S"/><task id="T" name="Review"/>'
    '<endEvent id="E"/><sequenceFlow id="F1" sourceRef="S" targetRef="T"/>'
    '<sequenceFlow id="F2" sourceRef="T" targetRef="E"/></process></definitions>'
)


def test_mcp_exposes_process_tools() -> None:
    async def run() -> tuple[list[str], bool]:
        async with Client(mcp_server.mcp) as client:
            result = await client.list_tools()
            checked = await client.call_tool("validate_bpmn", {"xml": BPMN})
            return [tool.name for tool in result.tools], checked.is_error

    names, validation_failed = asyncio.run(run())
    assert {"list_projects", "create_process", "get_bpmn_model", "validate_bpmn", "save_bpmn_model"} <= set(names)
    assert not validation_failed


def test_api_request_scopes_tenant_and_preserves_list_total(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["tenant"] = request.headers.get("X-DeliR-Tenant-ID")
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json=[{"id": "p1"}], headers={"X-DeliR-Total": "3"})

    real_client = httpx.Client
    monkeypatch.setattr(mcp_server.httpx, "Client", lambda **kwargs: real_client(
        transport=httpx.MockTransport(handler), **kwargs
    ))
    monkeypatch.setenv("DELIR_MCP_TENANT_ID", "tenant-a")
    monkeypatch.setenv("DELIR_MCP_API_TOKEN", "test-token")
    result = mcp_server.list_projects(limit=1)

    assert result == {"items": [{"id": "p1"}], "total": 3, "returned": 1, "limit": 1}
    assert seen["tenant"] == "tenant-a"
    assert seen["auth"] == "Bearer test-token"
    assert seen["url"].endswith("/v1/workspace/projects?limit=1")


def test_stale_element_edit_never_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_server, "get_bpmn_model", lambda _id: {
        "id": "b1", "xml": BPMN, "version_id": 8
    })
    writes = []
    monkeypatch.setattr(mcp_server, "save_bpmn_model", lambda *args: writes.append(args))

    with pytest.raises(mcp_server.DeliRApiError, match="cambiato"):
        mcp_server.update_process_element("b1", "T", expected_version_id=7, name="Approve")

    assert writes == []


def test_invalid_xml_never_calls_write_api(monkeypatch: pytest.MonkeyPatch) -> None:
    writes = []
    monkeypatch.setattr(mcp_server, "_request", lambda *args, **kwargs: writes.append((args, kwargs)))

    with pytest.raises(ValueError):
        mcp_server.save_bpmn_model("b1", "<bad", expected_version_id=2)

    assert writes == []


def test_remote_http_url_spoof_is_refused_before_token_forwarding(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DELIR_MCP_API_URL", "http://127.0.0.1:8000@attacker.example")
    monkeypatch.setenv("DELIR_MCP_API_TOKEN", "test-token")
    with pytest.raises(mcp_server.DeliRApiError, match="locale o HTTPS"):
        mcp_server.get_process("p1")


def test_save_reports_version_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"detail": "Il diagramma e' stato salvato altrove."})

    real_client = httpx.Client
    monkeypatch.setattr(mcp_server.httpx, "Client", lambda **kwargs: real_client(
        transport=httpx.MockTransport(handler), **kwargs
    ))
    with pytest.raises(mcp_server.DeliRApiError, match="HTTP 409"):
        mcp_server.save_bpmn_model("b1", BPMN, expected_version_id=4)


def test_element_edit_saves_from_expected_version(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_server, "get_bpmn_model", lambda _id: {
        "id": "b1", "xml": BPMN, "version_id": 8
    })
    saved = {}

    def fake_save(model_id: str, xml: str, version: int | None) -> dict:
        saved.update(model_id=model_id, xml=xml, version=version)
        return {"id": model_id, "version_id": 9}

    monkeypatch.setattr(mcp_server, "save_bpmn_model", fake_save)
    result = mcp_server.update_process_element("b1", "T", 8, name="Approve")

    assert result["version_id"] == 9
    assert saved["version"] == 8
    assert 'name="Approve"' in saved["xml"]
    assert 'sourceRef="S"' in saved["xml"]
