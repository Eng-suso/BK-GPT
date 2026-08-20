from pathlib import Path

from backend.graphs.common import build_tool_chat_subgraph
from backend.graphs.consulting.skill_context import load_markdown_skills, tool_prompt_block
from backend.graphs.consulting.subgraphs.clients.state import ClientsState
from backend.graphs.consulting.subgraphs.clients.tools import CLIENTS_TOOL_POLICY, clients_tools


SKILLS_DIR = Path(__file__).resolve().parent / "skills"

CLIENTS_SUBGRAPH_CONTRACT = """
Clients subgraph contract.

{tool_policy}

Check existing clients before creating a new one. Create records only when the
user is clearly asking to register a real client, not when brainstorming examples.

{skill_context}

{tool_prompts}
""".format(
    tool_policy=CLIENTS_TOOL_POLICY,
    skill_context=load_markdown_skills(SKILLS_DIR),
    tool_prompts=tool_prompt_block(clients_tools),
).strip()


def build_clients_subgraph(llm_with_tools, build_context_messages):
    return build_tool_chat_subgraph(
        state_schema=ClientsState,
        tools=clients_tools,
        llm_with_tools=llm_with_tools,
        build_context_messages=build_context_messages,
        subgraph_contract=CLIENTS_SUBGRAPH_CONTRACT,
        agent_node_name="clients_agent",
        tool_node_name="clients_tools",
    )
