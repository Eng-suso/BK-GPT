from pathlib import Path

from backend.graphs.common import build_tool_chat_subgraph
from backend.graphs.consulting.skill_context import load_markdown_skills, tool_prompt_block
from backend.graphs.process.subgraphs.evidence.state import ProcessEvidenceState
from backend.graphs.process.subgraphs.evidence.tools import EVIDENCE_TOOL_POLICY, evidence_tools


SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"

EVIDENCE_SUBGRAPH_CONTRACT = """
Process Evidence subgraph contract.

{tool_policy}

Use evidence synthesis as the mandatory bridge between raw notes and
ProcessUnderstanding. Keep facts, hypotheses, contradictions and gaps separate.

{skill_context}

{tool_prompts}
""".format(
    tool_policy=EVIDENCE_TOOL_POLICY,
    skill_context=load_markdown_skills(SKILLS_DIR),
    tool_prompts=tool_prompt_block(evidence_tools),
).strip()


def build_evidence_subgraph(llm_with_tools, build_context_messages):
    return build_tool_chat_subgraph(
        state_schema=ProcessEvidenceState,
        tools=evidence_tools,
        llm_with_tools=llm_with_tools,
        build_context_messages=build_context_messages,
        subgraph_contract=EVIDENCE_SUBGRAPH_CONTRACT,
        agent_node_name="process_evidence_agent",
        tool_node_name="process_evidence_tools",
    )
