from backend.graphs.canvas_edit.tools import canvas_tools
from backend.graphs.consulting.tools import consultant_tools
from backend.graphs.main.tools import main_tools
from backend.graphs.process.tools import process_tools
from backend.graphs.project.tools import project_tools
from backend.toolsets.bpmn import bpmn_review_tools
from backend.toolsets.memory import memory_tools
from backend.toolsets.web import web_research
from backend.toolsets.workspace import workspace_project_tools

tools_by_scope = {
    "main": main_tools,
    "consultant": consultant_tools,
    "project": project_tools,
    "process": process_tools,
    "canvas": canvas_tools,
}

# Compatibility export for older code paths that still expect one flat tool list.
tools = [
    *workspace_project_tools,
    *bpmn_review_tools,
    *memory_tools,
    web_research,
]
