from pathlib import Path

from backend.graphs.common import build_tool_chat_subgraph
from backend.graphs.consulting.skill_context import load_markdown_skills, tool_prompt_block
from backend.graphs.project.subgraphs.process_coordination.state import (
    ProjectProcessCoordinationState,
)
from backend.graphs.project.subgraphs.process_coordination.tools import (
    PROCESS_COORDINATION_TOOL_POLICY,
    process_coordination_tools,
)


SKILLS_DIR = Path(__file__).resolve().parent / "skills"

PROCESS_COORDINATION_SUBGRAPH_CONTRACT = """
Project Process Coordination subgraph contract.

{tool_policy}

Use the preloaded project snapshot and process coordination tools to coordinate
several processes as one enterprise project. Separate confirmed facts from
hypotheses. Prepare handoffs to Process Macro when the next step is deep work
on one process.

{skill_context}

{tool_prompts}
""".format(
    tool_policy=PROCESS_COORDINATION_TOOL_POLICY,
    skill_context=load_markdown_skills(SKILLS_DIR),
    tool_prompts=tool_prompt_block(process_coordination_tools),
).strip()


def build_process_coordination_subgraph(llm_with_tools, build_context_messages):
    return build_tool_chat_subgraph(
        state_schema=ProjectProcessCoordinationState,
        tools=process_coordination_tools,
        llm_with_tools=llm_with_tools,
        build_context_messages=build_context_messages,
        subgraph_contract=PROCESS_COORDINATION_SUBGRAPH_CONTRACT,
        agent_node_name="project_process_coordination_agent",
        tool_node_name="project_process_coordination_tools",
    )
