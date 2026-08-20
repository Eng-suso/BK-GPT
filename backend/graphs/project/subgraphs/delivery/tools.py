from backend.graphs.project.tools import (
    get_project_delivery_brief,
    prepare_deliverable_plan,
    prepare_project_status_update,
    record_project_next_action,
    record_project_risk,
)


DELIVERY_TOOL_POLICY = """
Project Delivery subagent tools.

The Delivery subagent owns project planning and delivery status for the current
project: phase, progress, milestones, deliverables, risks, blockers and next
actions. It does not own AS-IS process discovery, BPMN review or canvas XML edits.
""".strip()


delivery_tools = [
    get_project_delivery_brief,
    prepare_project_status_update,
    prepare_deliverable_plan,
    record_project_risk,
    record_project_next_action,
]
