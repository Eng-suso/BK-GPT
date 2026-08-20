from pathlib import Path

from backend.graphs.common import build_tool_chat_subgraph
from backend.graphs.consulting.skill_context import load_markdown_skills, tool_prompt_block
from backend.graphs.consulting.subgraphs.setup.state import SetupState
from backend.graphs.consulting.subgraphs.setup.tools import SETUP_TOOL_POLICY, setup_tools


SKILLS_DIR = Path(__file__).resolve().parent / "skills"

SETUP_SUBGRAPH_CONTRACT = """
Consult setup subgraph contract.

{tool_policy}

Setup is for initial records only. Keep created records minimal and explicit.
After setup, route ongoing project work to the Project Macro Agent and process
or BPMN work to the Process or Canvas Macro Agent.

{skill_context}

{tool_prompts}
""".format(
    tool_policy=SETUP_TOOL_POLICY,
    skill_context=load_markdown_skills(SKILLS_DIR),
    tool_prompts=tool_prompt_block(setup_tools),
).strip()


def build_setup_subgraph(llm_with_tools, build_context_messages):
    return build_tool_chat_subgraph(
        state_schema=SetupState,
        tools=setup_tools,
        llm_with_tools=llm_with_tools,
        build_context_messages=build_context_messages,
        subgraph_contract=SETUP_SUBGRAPH_CONTRACT,
        agent_node_name="setup_agent",
        tool_node_name="setup_tools",
    )
