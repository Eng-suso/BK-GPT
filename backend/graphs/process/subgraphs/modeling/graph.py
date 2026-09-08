from pathlib import Path

from backend.graphs.common import build_tool_chat_subgraph
from backend.graphs.consulting.skill_context import load_markdown_skills, tool_prompt_block
from backend.graphs.process.state import ProcessState
from backend.graphs.process.subgraphs.modeling.tools import MODELING_TOOL_POLICY, modeling_tools


SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"

MODELING_SUBGRAPH_CONTRACT = """
Process Modeling subgraph contract.

{tool_policy}

Use ProcessUnderstanding as the canonical semantic context. A BPMNSemanticModel
may be derived only from ProcessUnderstanding, not directly from free text.
For new AS-IS mapping, build a consultant-grade ProcessUnderstanding first:
separate actors from BPMN participants, classify pool/lane/black-box candidates,
assign every activity to an actor, preserve document requirements and business
rules, separate main path from alternatives, and provide readable flow_edges for
the future canvas arrows. Preserve assumptions, gaps and model warnings.

{skill_context}

{tool_prompts}
""".format(
    tool_policy=MODELING_TOOL_POLICY,
    skill_context=load_markdown_skills(SKILLS_DIR),
    tool_prompts=tool_prompt_block(modeling_tools),
).strip()


def build_modeling_subgraph(llm_with_tools, build_context_messages):
    """
    Construct a tool-enabled subgraph for process modeling.
    
    The subgraph uses ``ProcessState`` and enforces the modeling contract, including
    ``ProcessUnderstanding`` as the canonical context and preservation of AS-IS
    modeling details such as actors, participants, documents, rules, paths,
    assumptions, gaps, and warnings. Construction does not persist data or perform
    other external side effects.
    
    Args:
        llm_with_tools: Language model configured with the modeling tools.
        build_context_messages: Callable that builds context messages from process
            state.
    
    Returns:
        A configured tool-enabled process-modeling subgraph.
    """
    return build_tool_chat_subgraph(
        state_schema=ProcessState,
        tools=modeling_tools,
        llm_with_tools=llm_with_tools,
        build_context_messages=build_context_messages,
        subgraph_contract=MODELING_SUBGRAPH_CONTRACT,
        agent_node_name="process_modeling_agent",
        tool_node_name="process_modeling_tools",
        # La conclusione della passata va nel dossier di lavoro, non nella
        # chat: a parlare al consulente e' `process_report`, una volta sola.
        findings_channel="specialist_findings",
        specialist="modeling",
    )
