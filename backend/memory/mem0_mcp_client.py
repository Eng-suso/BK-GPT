from __future__ import annotations

import asyncio
import json
import shlex
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from backend.settings import settings


MEM0_MCP_TOOL_NAMES = {
    "add_memory",
    "search_memories",
    "get_memories",
    "get_memory",
    "update_memory",
    "delete_memory",
    "delete_all_memories",
    "delete_entities",
    "list_entities",
    "list_events",
    "get_event_status",
}


class Mem0MCPError(RuntimeError):
    pass


def mcp_enabled() -> bool:
    return settings.mem0_mcp_enabled


def _compact(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if value is not None and value != "" and value != [] and value != {}
    }


def _parse_json_object(value: str, setting_name: str) -> dict[str, Any]:
    if not value.strip():
        return {}

    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise Mem0MCPError(f"{setting_name} must be valid JSON.") from exc

    if not isinstance(parsed, dict):
        raise Mem0MCPError(f"{setting_name} must be a JSON object.")

    return parsed


def _parse_args(value: str) -> list[str]:
    cleaned = value.strip()
    if not cleaned:
        return []

    if cleaned.startswith("["):
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise Mem0MCPError("MEM0_MCP_ARGS must be JSON array or shell-style args.") from exc
        if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
            raise Mem0MCPError("MEM0_MCP_ARGS JSON value must be an array of strings.")
        return parsed

    return shlex.split(cleaned, posix=False)


def _authorization_header() -> dict[str, str]:
    if not settings.mem0_api_key:
        return {}

    scheme = settings.mem0_mcp_auth_scheme.strip()
    if not scheme:
        return {}

    return {"Authorization": f"{scheme} {settings.mem0_api_key}"}


def _server_config() -> dict[str, Any]:
    if not settings.mem0_mcp_enabled:
        raise Mem0MCPError("Mem0 MCP disattivato: imposta MEM0_MCP_ENABLED=true.")

    transport = settings.mem0_mcp_transport.strip().lower()

    if transport in {"http", "streamable_http", "sse"}:
        url = settings.mem0_mcp_url.strip()
        if not url:
            raise Mem0MCPError("MEM0_MCP_URL mancante.")

        headers = {
            **_authorization_header(),
            **_parse_json_object(settings.mem0_mcp_headers_json, "MEM0_MCP_HEADERS_JSON"),
        }
        return _compact(
            {
                "transport": "http" if transport == "streamable_http" else transport,
                "url": url,
                "headers": headers,
            }
        )

    if transport == "stdio":
        command = (settings.mem0_mcp_command or "").strip()
        if not command:
            raise Mem0MCPError("MEM0_MCP_COMMAND mancante per transport stdio.")

        env = _parse_json_object(settings.mem0_mcp_env_json, "MEM0_MCP_ENV_JSON")
        return _compact(
            {
                "transport": "stdio",
                "command": command,
                "args": _parse_args(settings.mem0_mcp_args),
                "env": env,
            }
        )

    raise Mem0MCPError(f"MEM0_MCP_TRANSPORT non supportato: {settings.mem0_mcp_transport}")


async def _load_tools():
    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
    except ImportError as exc:
        raise Mem0MCPError(
            "Dipendenza mancante: installa langchain-mcp-adapters per usare Mem0 MCP."
        ) from exc

    client = MultiServerMCPClient({"mem0": _server_config()})
    return await client.get_tools()


def _select_tool(tools: list[Any], tool_name: str):
    if tool_name not in MEM0_MCP_TOOL_NAMES:
        raise Mem0MCPError(f"Tool Mem0 MCP non consentito: {tool_name}")

    for tool in tools:
        name = getattr(tool, "name", "")
        if name == tool_name or name.endswith(f"__{tool_name}"):
            return tool

    available = ", ".join(sorted(getattr(tool, "name", "") for tool in tools))
    raise Mem0MCPError(f"Tool Mem0 MCP non disponibile: {tool_name}. Disponibili: {available}")


async def acall_mem0_tool(tool_name: str, arguments: dict[str, Any]) -> Any:
    tools = await _load_tools()
    tool = _select_tool(tools, tool_name)
    return await tool.ainvoke(_compact(arguments))


def _run_async(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(lambda: asyncio.run(coro)).result()


def call_mem0_tool(tool_name: str, arguments: dict[str, Any]) -> Any:
    return _run_async(acall_mem0_tool(tool_name, arguments))


def add_memory(
    *,
    text: str,
    user_id: str,
    metadata: dict[str, Any] | None = None,
    infer: bool = True,
) -> Any:
    return call_mem0_tool(
        "add_memory",
        {
            "text": text,
            "user_id": user_id,
            "metadata": metadata or {},
            "infer": infer,
        },
    )


def search_memories(
    *,
    query: str,
    filters: dict[str, Any],
    limit: int = 5,
) -> Any:
    return call_mem0_tool(
        "search_memories",
        {
            "query": query,
            "filters": filters,
            "limit": limit,
        },
    )


def get_memories(
    *,
    filters: dict[str, Any],
    page: int = 1,
    limit: int = 20,
) -> Any:
    return call_mem0_tool(
        "get_memories",
        {
            "filters": filters,
            "page": page,
            "limit": limit,
        },
    )


def get_memory(*, memory_id: str) -> Any:
    return call_mem0_tool("get_memory", {"memory_id": memory_id})


def update_memory(
    *,
    memory_id: str,
    text: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Any:
    return call_mem0_tool(
        "update_memory",
        {
            "memory_id": memory_id,
            "text": text,
            "metadata": metadata or {},
        },
    )


def delete_memory(*, memory_id: str) -> Any:
    return call_mem0_tool("delete_memory", {"memory_id": memory_id})


def delete_all_memories(*, filters: dict[str, Any]) -> Any:
    return call_mem0_tool("delete_all_memories", {"filters": filters})


def delete_entities(*, entity_type: str, entity_id: str) -> Any:
    return call_mem0_tool(
        "delete_entities",
        {
            "entity_type": entity_type,
            "entity_id": entity_id,
        },
    )


def list_entities(
    *,
    entity_type: str | None = None,
    page: int = 1,
    limit: int = 50,
) -> Any:
    return call_mem0_tool(
        "list_entities",
        {
            "entity_type": entity_type,
            "page": page,
            "limit": limit,
        },
    )


def list_events(
    *,
    filters: dict[str, Any] | None = None,
    page: int = 1,
    limit: int = 50,
) -> Any:
    return call_mem0_tool(
        "list_events",
        {
            "filters": filters or {},
            "page": page,
            "limit": limit,
        },
    )


def get_event_status(*, event_id: str) -> Any:
    return call_mem0_tool("get_event_status", {"event_id": event_id})
