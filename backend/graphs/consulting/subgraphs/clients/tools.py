from backend.toolsets.workspace import get_workspace_overview, list_workspace_clients, manage_client_record


CLIENTS_TOOL_POLICY = """
Clients subagent tools.

The Clients subagent owns client-level workspace records from the Consulting Chat.
It can list existing clients, create explicit real client records and inspect projects
to understand client/project linkage. It does not own project execution.
""".strip()


clients_tools = [
    get_workspace_overview,
    list_workspace_clients,
    manage_client_record,
]
