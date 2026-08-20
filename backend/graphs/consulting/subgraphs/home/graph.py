from pathlib import Path

from backend.graphs.common import build_tool_chat_subgraph
from backend.graphs.consulting.skill_context import load_markdown_skills, tool_prompt_block
from backend.graphs.consulting.subgraphs.home.state import HomeState
from backend.graphs.consulting.subgraphs.home.tools import HOME_TOOL_POLICY, home_tools


SKILLS_DIR = Path(__file__).resolve().parent / "skills"

HOME_SUBGRAPH_CONTRACT = """
Home subgraph contract.

{tool_policy}

Use Home procedural memory for dashboard synthesis. Keep the response focused on
workspace status, priorities, risks and next actions. If the user asks to mutate
clients or projects, explain that the request belongs to Clients or Project.

{skill_context}

{tool_prompts}
""".format(
    tool_policy=HOME_TOOL_POLICY,
    skill_context=load_markdown_skills(SKILLS_DIR),
    tool_prompts=tool_prompt_block(home_tools),
).strip()


def build_home_subgraph(llm_with_tools, build_context_messages):
    return build_tool_chat_subgraph(
        state_schema=HomeState,
        tools=home_tools,
        llm_with_tools=llm_with_tools,
        build_context_messages=build_context_messages,
        subgraph_contract=HOME_SUBGRAPH_CONTRACT,
        agent_node_name="home_agent",
        tool_node_name="home_tools",
    )
