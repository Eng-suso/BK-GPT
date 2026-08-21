from pathlib import Path

from backend.graphs.common import build_tool_chat_subgraph
from backend.graphs.consulting.skill_context import load_markdown_skills, tool_prompt_block
from backend.graphs.process.subgraphs.discovery.state import ProcessDiscoveryState
from backend.graphs.process.subgraphs.discovery.tools import DISCOVERY_TOOL_POLICY, discovery_tools


SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"

DISCOVERY_SUBGRAPH_CONTRACT = """
Process Discovery subgraph contract.

{tool_policy}

Use ProcessUnderstanding as the target semantic context, but do not force
modeling before discovery is ready. Return confirmed facts, hypotheses, gaps,
next sources and readiness.

{skill_context}

{tool_prompts}
""".format(
    tool_policy=DISCOVERY_TOOL_POLICY,
    skill_context=load_markdown_skills(SKILLS_DIR),
    tool_prompts=tool_prompt_block(discovery_tools),
).strip()


def build_discovery_subgraph(llm_with_tools, build_context_messages):
    return build_tool_chat_subgraph(
        state_schema=ProcessDiscoveryState,
        tools=discovery_tools,
        llm_with_tools=llm_with_tools,
        build_context_messages=build_context_messages,
        subgraph_contract=DISCOVERY_SUBGRAPH_CONTRACT,
        agent_node_name="process_discovery_agent",
        tool_node_name="process_discovery_tools",
    )
