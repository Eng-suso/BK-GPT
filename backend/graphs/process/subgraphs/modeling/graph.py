from pathlib import Path

from backend.graphs.common import build_tool_chat_subgraph
from backend.graphs.consulting.skill_context import load_markdown_skills, tool_prompt_block
from backend.graphs.process.subgraphs.modeling.state import ProcessModelingState
from backend.graphs.process.subgraphs.modeling.tools import MODELING_TOOL_POLICY, modeling_tools


SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"

MODELING_SUBGRAPH_CONTRACT = """
Process Modeling subgraph contract.

{tool_policy}

Use ProcessUnderstanding as the canonical semantic context. A BPMNSemanticModel
may be derived only from ProcessUnderstanding, not directly from free text.
Preserve assumptions, gaps and model warnings.

{skill_context}

{tool_prompts}
""".format(
    tool_policy=MODELING_TOOL_POLICY,
    skill_context=load_markdown_skills(SKILLS_DIR),
    tool_prompts=tool_prompt_block(modeling_tools),
).strip()


def build_modeling_subgraph(llm_with_tools, build_context_messages):
    return build_tool_chat_subgraph(
        state_schema=ProcessModelingState,
        tools=modeling_tools,
        llm_with_tools=llm_with_tools,
        build_context_messages=build_context_messages,
        subgraph_contract=MODELING_SUBGRAPH_CONTRACT,
        agent_node_name="process_modeling_agent",
        tool_node_name="process_modeling_tools",
    )
