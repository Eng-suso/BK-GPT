from backend.toolsets.workspace import (
    create_initial_workspace_setup,
    get_workspace_overview,
    validate_initial_workspace_setup,
)


SETUP_TOOL_POLICY = """
Consult setup subagent tools.

The setup subagent owns explicit initial workspace setup from the Consulting Chat.
It can create clients, initial projects, process stubs, sources and open decisions
when the user clearly asks to register real workspace records.
""".strip()


setup_tools = [
    get_workspace_overview,
    validate_initial_workspace_setup,
    create_initial_workspace_setup,
]
