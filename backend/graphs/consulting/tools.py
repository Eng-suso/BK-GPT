import json

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from backend.toolsets.memory import (
    remember_consultant_fact,
    retrieve_consulting_context,
    retrieve_consulting_graph_context,
    save_episode,
)
from backend.toolsets.web import web_research
from backend.toolsets.workspace import get_workspace_overview


class DelegationPayloadInput(BaseModel):
    target_owner: str = Field(
        description="Destination owner: home, clients, setup, project_macro, process_macro, or canvas_macro."
    )
    user_request: str = Field(description="Latest user request to delegate.")
    expected_result: str = Field(description="What the receiving owner should produce.")
    reason: str = Field(description="Why this owner is responsible.")
    known_context: str = Field(default="", description="Only the minimal known ids or facts needed for delegation.")


@tool(args_schema=DelegationPayloadInput)
def prepare_delegation_payload(
    target_owner: str,
    user_request: str,
    expected_result: str,
    reason: str,
    known_context: str = "",
) -> str:
    """
    Purpose: create a narrow structured delegation payload for another subgraph or macro agent.
    Use when Consult Macro decides the work belongs to Home, Clients, Setup, Project, Process or Canvas.
    Do not use to execute the delegated work; this only prepares the handoff.
    """
    return "Delegation payload\n" + json.dumps(
        {
            "status": "prepared",
            "action": "prepare_delegation_payload",
            "target_owner": target_owner,
            "user_request": user_request,
            "expected_result": expected_result,
            "reason": reason,
            "known_context": known_context,
        },
        ensure_ascii=False,
        indent=2,
    )


CONSULTING_TOOL_POLICY = """
Consulting agent tools.

The consulting agent owns general consultant memory, business context,
method, positioning, external research and top-level orchestration.
It must delegate Home, Clients, setup, Project, Process and Canvas operations
to the correct subgraph or macro agent instead of using broad generic tools.
""".strip()


consultant_memory_tools = [
    remember_consultant_fact,
    retrieve_consulting_context,
    retrieve_consulting_graph_context,
    save_episode,
]

consultant_tools = [
    get_workspace_overview,
    prepare_delegation_payload,
    *consultant_memory_tools,
    web_research,
]
