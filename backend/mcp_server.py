"""Local MCP adapter for DeliR's authenticated workspace API.

The API remains the authority for tenant isolation, BPMN persistence, and
version conflicts. This process is intended for a trusted local MCP host.
"""

from __future__ import annotations

import os
from urllib.parse import quote, urlsplit

import httpx
from mcp.server import MCPServer

from backend.workspace_services.bpmn_canvas_edit import (
    preview_bpmn_xml_change,
    update_bpmn_element,
    validate_bpmn_xml,
)


mcp = MCPServer(
    "DeliR",
    instructions=(
        "Use DeliR as the source of truth for business processes. Read a model "
        "and its version before editing. Preview changes before saving. Never "
        "claim a BPMN model is fully BPMN 2.0 compliant based only on the "
        "lightweight validation tool."
    ),
)


class DeliRApiError(RuntimeError):
    """An authenticated DeliR API request failed."""


def _model_path(model_id: str) -> str:
    if not model_id.strip() or model_id in {".", ".."}:
        raise ValueError("bpmn_model_id obbligatorio.")
    return f"/v1/workspace/bpmn-models/{quote(model_id, safe='')}"


def _request(method: str, path: str, *, params: dict | None = None, json: dict | None = None):
    base_url = os.getenv("DELIR_MCP_API_URL", "http://127.0.0.1:8000").rstrip("/")
    tenant_id = os.getenv("DELIR_MCP_TENANT_ID", "local").strip()
    token = os.getenv("DELIR_MCP_API_TOKEN", "").strip()
    if not tenant_id:
        raise DeliRApiError("DELIR_MCP_TENANT_ID non configurato.")
    parsed_url = urlsplit(base_url)
    is_local_http = parsed_url.scheme == "http" and parsed_url.hostname in {"127.0.0.1", "localhost"}
    if (
        not (parsed_url.scheme == "https" or is_local_http)
        or not parsed_url.hostname
        or parsed_url.username
        or parsed_url.password
        or parsed_url.query
        or parsed_url.fragment
    ):
        raise DeliRApiError("DELIR_MCP_API_URL deve essere locale o HTTPS.")
    headers = {"X-DeliR-Tenant-ID": tenant_id, "X-DeliR-User-ID": "mcp-local"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with httpx.Client(timeout=20.0, follow_redirects=False) as client:
            response = client.request(method, base_url + path, headers=headers, params=params, json=json)
    except httpx.RequestError as exc:
        raise DeliRApiError("API DeliR non raggiungibile.") from exc
    if response.is_error:
        try:
            detail = response.json().get("detail", "")
        except (ValueError, AttributeError):
            detail = ""
        if not isinstance(detail, str):
            detail = ""
        raise DeliRApiError(f"API DeliR: HTTP {response.status_code}. {detail[:300]}")
    payload = response.json()
    if path == "/v1/workspace/projects" and method == "GET":
        return {
            "items": payload,
            "total": int(response.headers.get("X-DeliR-Total", len(payload))),
            "returned": len(payload),
            "limit": params["limit"] if params else None,
        }
    return payload


@mcp.tool()
def list_projects(limit: int = 50) -> dict:
    """List the current tenant's active projects (up to 100)."""
    if not 1 <= limit <= 100:
        raise ValueError("limit deve essere tra 1 e 100.")
    return _request("GET", "/v1/workspace/projects", params={"limit": limit})


@mcp.tool()
def list_processes(project_id: str) -> list[dict]:
    """List processes in one project of the current tenant."""
    return _request("GET", f"/v1/workspace/projects/{quote(project_id, safe='')}/processes")


@mcp.tool()
def get_process(process_id: str) -> dict:
    """Read process metadata, including the BPMN model ID."""
    return _request("GET", f"/v1/workspace/processes/{quote(process_id, safe='')}")


@mcp.tool()
def create_process(project_id: str, name: str) -> dict:
    """Create an empty process record in a project; save its BPMN separately.

    The returned `bpmn_model_id` identifies the new canvas. This operation
    persists a process even if a later model save fails.
    """
    if not project_id.strip() or not name.strip():
        raise ValueError("project_id e name sono obbligatori.")
    return _request(
        "POST",
        f"/v1/workspace/projects/{quote(project_id, safe='')}/processes",
        json={"name": name.strip()},
    )


@mcp.tool()
def get_bpmn_model(bpmn_model_id: str) -> dict:
    """Read the authoritative BPMN XML and version ID before editing."""
    return _request("GET", _model_path(bpmn_model_id))


@mcp.tool()
def validate_bpmn(xml: str) -> dict:
    """Check XML structure, basic BPMN references and renderability warnings.

    This is a lightweight check, not complete BPMN 2.0 conformance.
    """
    return validate_bpmn_xml(xml)


@mcp.tool()
def preview_bpmn_change(bpmn_model_id: str, proposed_xml: str, expected_version_id: int | None) -> dict:
    """Compare proposed XML with the current model without saving anything."""
    current = get_bpmn_model(bpmn_model_id)
    if current["version_id"] != expected_version_id:
        raise DeliRApiError("Il modello e' cambiato: rileggilo prima di proporre modifiche.")
    if not current.get("xml"):
        return {"current_version_id": expected_version_id, "validation": validate_bpmn_xml(proposed_xml)}
    return {
        "current_version_id": expected_version_id,
        **preview_bpmn_xml_change(current["xml"], proposed_xml),
    }


@mcp.tool()
def save_bpmn_model(bpmn_model_id: str, xml: str, expected_version_id: int | None) -> dict:
    """Save BPMN XML after validation, using the version read by the caller.

    A concurrent save returns a conflict. The DeliR API performs its own write
    validation and creates the authoritative version snapshot.
    """
    report = validate_bpmn_xml(xml)
    if not report["valid"]:
        raise ValueError(f"Modello non valido: {report['issues']}")
    return _request(
        "PUT",
        _model_path(bpmn_model_id),
        json={"xml": xml, "expected_version_id": expected_version_id},
    )


@mcp.tool()
def update_process_element(
    bpmn_model_id: str,
    element_id: str,
    expected_version_id: int | None,
    name: str | None = None,
    documentation: str | None = None,
) -> dict:
    """Rename or document one BPMN element and save a new model version."""
    current = get_bpmn_model(bpmn_model_id)
    if current["version_id"] != expected_version_id:
        raise DeliRApiError("Il modello e' cambiato: rileggilo prima di modificarlo.")
    if not current.get("xml"):
        raise ValueError("Il modello BPMN non contiene XML da modificare.")
    updated_xml, change = update_bpmn_element(
        current["xml"], element_id, name=name, documentation=documentation
    )
    saved = save_bpmn_model(bpmn_model_id, updated_xml, expected_version_id)
    return {"change": change, "bpmn_model_id": saved["id"], "version_id": saved["version_id"]}


if __name__ == "__main__":
    mcp.run()
