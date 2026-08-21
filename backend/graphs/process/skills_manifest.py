PROCESS_SKILLS_BY_OWNER = {
    "process_macro": [
        "process_macro_orchestration",
        "process_scope_governance",
        "process_graph_memory_governance",
        "canvas_handoff_governance",
    ],
    "discovery_subgraph": [
        "process_discovery",
        "process_scope_governance",
    ],
    "evidence_subgraph": [
        "evidence_synthesis",
        "process_graph_memory_governance",
    ],
    "modeling_subgraph": [
        "process_modeling",
        "canvas_handoff_governance",
    ],
}


def required_skills_for(owner: str) -> list[str]:
    return PROCESS_SKILLS_BY_OWNER.get(owner, [])
