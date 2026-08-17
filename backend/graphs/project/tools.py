from backend.toolsets.memory import memory_tools
from backend.toolsets.web import web_research
from backend.toolsets.workspace import workspace_project_tools


PROJECT_TOOL_POLICY = """
Project agent tools.

The project agent owns workspace records at client/project level:
clients, projects, processes, sources and decisions. It can use memory and
web research for context, but canvas-level BPMN edits belong to canvas_edit.
""".strip()


project_tools = [
    *workspace_project_tools,
    *memory_tools,
    web_research,
]
