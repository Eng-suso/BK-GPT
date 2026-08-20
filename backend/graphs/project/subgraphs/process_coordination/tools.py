from backend.graphs.project.tools import (
    get_process_readiness_matrix,
    get_project_process_map,
    identify_cross_process_dependencies,
    prepare_process_handoff,
    prepare_process_workplan,
    record_cross_process_issue,
)


PROCESS_COORDINATION_TOOL_POLICY = """
Project Process Coordination subagent tools.

The Process Coordination subagent owns enterprise coordination across multiple
processes inside the current project: readiness matrix, sequencing, dependencies,
interview needs, cross-process blockers and handoff preparation to Process Macro.
It does not perform deep AS-IS discovery for one process and does not edit BPMN.
""".strip()


process_coordination_tools = [
    get_project_process_map,
    get_process_readiness_matrix,
    identify_cross_process_dependencies,
    prepare_process_workplan,
    prepare_process_handoff,
    record_cross_process_issue,
]
