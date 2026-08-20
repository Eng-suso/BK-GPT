from backend.toolsets.workspace import (
    get_workspace_overview,
    prepare_home_dashboard_update,
    record_home_priority,
    record_home_risk,
    record_next_action,
)


HOME_TOOL_POLICY = """
Home subagent tools.

The Home subagent owns dashboard-level reading and synthesis across the workspace.
It can inspect clients and projects to summarize priorities, risks and next actions.
It does not create or mutate workspace records.
""".strip()


home_tools = [
    get_workspace_overview,
    prepare_home_dashboard_update,
    record_home_priority,
    record_home_risk,
    record_next_action,
]
