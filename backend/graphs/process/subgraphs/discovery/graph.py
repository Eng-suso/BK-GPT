from pathlib import Path

from backend.graphs.common import build_tool_chat_subgraph
from backend.graphs.consulting.skill_context import load_markdown_skills, tool_prompt_block
from backend.graphs.process.state import ProcessState
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
    """Build the process-discovery chat subgraph with its configured state, tools, and contract.
    
    Args:
        llm_with_tools: Language model configured for tool use.
        build_context_messages: Callable that builds context messages for the subgraph.
    
    Returns:
        The configured process-discovery chat subgraph.
    """
    return build_tool_chat_subgraph(
        state_schema=ProcessState,
        tools=discovery_tools,
        llm_with_tools=llm_with_tools,
        build_context_messages=build_context_messages,
        subgraph_contract=DISCOVERY_SUBGRAPH_CONTRACT,
        agent_node_name="process_discovery_agent",
        tool_node_name="process_discovery_tools",
        # La conclusione della passata va nel dossier di lavoro, non nella
        # chat: a parlare al consulente e' `process_report`, una volta sola.
        findings_channel="specialist_findings",
        specialist="discovery",
    )
