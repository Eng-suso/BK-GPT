from backend.toolsets.memory import memory_tools
from backend.toolsets.web import web_research
from backend.toolsets.workspace import workspace_project_tools


CONSULTING_TOOL_POLICY = """
Consulting agent tools.

The consulting agent owns general consultant memory, business context,
method, positioning, external research and top-level workspace setup.
It can create clients, projects, initial processes, sources and decisions
when the user asks to set up real workspace records from the main consultant chat.
Canvas-level BPMN XML edits still belong to canvas_edit.
""".strip()


consultant_tools = [
    *workspace_project_tools,
    *memory_tools,
    web_research,
]
