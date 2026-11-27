"""Private, single-tenant HTTP pilot for a personal Claude connector.

This is not the multi-user OAuth endpoint. The caller must present a separate
pilot bearer token; the backend API token stays in this server's environment.
"""

from __future__ import annotations

import os
from hmac import compare_digest

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse

from backend import mcp_server


def _public_host() -> str | None:
    host = os.getenv("DELIR_MCP_PILOT_PUBLIC_HOST", "").strip().lower()
    if not host:
        return None
    if any(char in host for char in "/:@?#\\ ") or host in {"localhost", "127.0.0.1"}:
        raise ValueError("DELIR_MCP_PILOT_PUBLIC_HOST deve essere solo un hostname pubblico.")
    return host


def create_app():
    """Build a fail-closed MCP HTTP app with a narrow hostname allowlist."""
    pilot = MCPServer(
        "DeliR personal pilot",
        instructions=(
            "Personal DeliR pilot. Read the process model and its version before "
            "making claims. BPMN validation is limited to the checks DeliR exposes."
        ),
    )
    for tool in (
        mcp_server.list_projects,
        mcp_server.list_processes,
        mcp_server.get_process,
        mcp_server.get_bpmn_model,
        mcp_server.validate_bpmn,
        mcp_server.preview_bpmn_change,
    ):
        pilot.tool()(tool)
    if os.getenv("DELIR_MCP_PILOT_ALLOW_WRITES") == "1":
        for tool in (
            mcp_server.create_process,
            mcp_server.save_bpmn_model,
            mcp_server.update_process_element,
        ):
            pilot.tool()(tool)

    hosts = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
    public_host = _public_host()
    if public_host:
        hosts.extend([public_host, f"{public_host}:*"])
    inner = pilot.streamable_http_app(
        json_response=True,
        stateless_http=True,
        transport_security=TransportSecuritySettings(allowed_hosts=hosts),
    )

    async def app(scope, receive, send):
        if scope["type"] != "http":
            await inner(scope, receive, send)
            return
        token = os.getenv("DELIR_MCP_PILOT_TOKEN", "")
        if len(token) < 32:
            await JSONResponse({"error": "Pilot token not configured"}, status_code=503)(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        authorization = headers.get(b"authorization", b"").decode("ascii", errors="ignore")
        if not authorization.startswith("Bearer ") or not compare_digest(authorization[7:], token):
            await JSONResponse({"error": "Unauthorized"}, status_code=401)(scope, receive, send)
            return
        await inner(scope, receive, send)

    return app


app = create_app()
