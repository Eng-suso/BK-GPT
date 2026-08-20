from pathlib import Path

from backend.graphs.common import build_tool_chat_subgraph
from backend.graphs.consulting.skill_context import load_markdown_skills, tool_prompt_block
from backend.graphs.project.subgraphs.delivery.state import ProjectDeliveryState
from backend.graphs.project.subgraphs.delivery.tools import DELIVERY_TOOL_POLICY, delivery_tools


SKILLS_DIR = Path(__file__).resolve().parent / "skills"

DELIVERY_SUBGRAPH_CONTRACT = """
Project Delivery subgraph contract.

{tool_policy}

Use the preloaded project snapshot and delivery tools to produce concise,
enterprise-grade project plans, status updates, risk summaries and deliverable
plans. If the request is about coordinating several processes, route that work
back to Project Process Coordination.

{skill_context}

{tool_prompts}
""".format(
    tool_policy=DELIVERY_TOOL_POLICY,
    skill_context=load_markdown_skills(SKILLS_DIR),
    tool_prompts=tool_prompt_block(delivery_tools),
).strip()


def build_delivery_subgraph(llm_with_tools, build_context_messages):
    return build_tool_chat_subgraph(
        state_schema=ProjectDeliveryState,
        tools=delivery_tools,
        llm_with_tools=llm_with_tools,
        build_context_messages=build_context_messages,
        subgraph_contract=DELIVERY_SUBGRAPH_CONTRACT,
        agent_node_name="project_delivery_agent",
        tool_node_name="project_delivery_tools",
    )
