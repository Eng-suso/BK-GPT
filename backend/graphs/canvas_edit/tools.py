from backend.toolsets.bpmn import (
    add_canvas_bpmn_element,
    approve_canvas_bpmn_review,
    connect_canvas_bpmn_elements,
    delete_canvas_bpmn_element,
    layout_canvas_bpmn,
    list_canvas_bpmn_elements,
    list_canvas_bpmn_versions,
    prepare_canvas_bpmn_review,
    preview_canvas_bpmn_change,
    read_canvas_bpmn_xml,
    reconnect_canvas_bpmn_flow,
    replace_canvas_bpmn_xml,
    restore_canvas_bpmn_version,
    update_canvas_bpmn_element,
    validate_canvas_bpmn,
)
from backend.toolsets.memory import memory_tools
from backend.toolsets.web import web_research
from backend.toolsets.workspace import workspace_canvas_tools


CANVAS_TOOL_POLICY = """
Canvas edit agent tools.

The canvas agent owns current BPMN canvas inspection and deterministic edits.
It can read/list/add/update/delete/connect/reconnect/validate/layout/replace
canvas BPMN XML, prepare/approve canvas review, manage saved BPMN versions and
record sources or decisions linked to the model. Project/process creation belongs
to project/process agents.
""".strip()


canvas_tools = [
    *workspace_canvas_tools,
    read_canvas_bpmn_xml,
    list_canvas_bpmn_elements,
    update_canvas_bpmn_element,
    add_canvas_bpmn_element,
    delete_canvas_bpmn_element,
    connect_canvas_bpmn_elements,
    reconnect_canvas_bpmn_flow,
    validate_canvas_bpmn,
    preview_canvas_bpmn_change,
    layout_canvas_bpmn,
    replace_canvas_bpmn_xml,
    list_canvas_bpmn_versions,
    restore_canvas_bpmn_version,
    prepare_canvas_bpmn_review,
    approve_canvas_bpmn_review,
    *memory_tools,
    web_research,
]
