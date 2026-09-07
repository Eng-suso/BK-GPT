from backend.toolsets.workspace import (
    create_initial_workspace_setup,
    create_workspace_project,
    get_workspace_overview,
    list_workspace_clients,
    validate_initial_workspace_setup,
)


SETUP_TOOL_POLICY = """
Consult setup subagent tools.

The setup subagent owns the workspace records an engagement needs before anyone
can work in it. It can create clients, projects, process stubs, sources and open
decisions when the user clearly asks to register real workspace records.

Creating a project for a client that already exists is setup, not project work:
resolve the client with list_workspace_clients, then create the project with
create_workspace_project and report the project id back. Use
create_initial_workspace_setup only when the client has to be created too, or
when a process stub, source or decision goes with it. Once the records exist,
ongoing work belongs to the Project, Process or Canvas macro agents.
""".strip()


setup_tools = [
    get_workspace_overview,
    list_workspace_clients,
    validate_initial_workspace_setup,
    create_workspace_project,
    create_initial_workspace_setup,
]
