from backend.toolsets.bpmn import prepare_process_bpmn_review, read_process_bpmn_xml
from backend.toolsets.memory import memory_tools
from backend.toolsets.web import web_research
from backend.toolsets.workspace import workspace_process_tools


PROCESS_TOOL_POLICY = """
Process agent tools.

The process agent owns AS-IS collection and process-level review. It can read
the process BPMN XML and prepare a BPMN review through ProcessUnderstanding
and BPMNSemanticModel. It cannot approve final canvas generation or perform
direct canvas XML edits.
""".strip()


process_tools = [
    *workspace_process_tools,
    read_process_bpmn_xml,
    prepare_process_bpmn_review,
    *memory_tools,
    web_research,
]
