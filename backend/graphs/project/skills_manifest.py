PROJECT_SKILLS_MANIFEST = {
    "project_macro": {
        "required": [
            "project_macro_orchestration",
            "project_scope_governance",
            "project_delegation_policy",
        ],
        "optional": [
            "project_status_synthesis",
            "multi_process_coordination",
        ],
        "forbidden": [
            "process_discovery",
            "canvas_bpmn_editing",
        ],
    },
    "delivery_subgraph": {
        "required": [
            "project_delivery_governance",
            "project_status_synthesis",
            "deliverable_planning",
            "risk_and_blocker_management",
        ],
        "optional": [],
        "forbidden": [
            "process_dependency_mapping",
            "canvas_bpmn_editing",
        ],
    },
    "process_coordination_subgraph": {
        "required": [
            "multi_process_coordination",
            "process_dependency_mapping",
            "interview_planning_by_process",
            "process_handoff_governance",
        ],
        "optional": [],
        "forbidden": [
            "single_process_discovery",
            "canvas_bpmn_editing",
        ],
    },
}


def required_skills_for(agent_name: str) -> list[str]:
    return list(PROJECT_SKILLS_MANIFEST.get(agent_name, {}).get("required", []))


def forbidden_skills_for(agent_name: str) -> list[str]:
    return list(PROJECT_SKILLS_MANIFEST.get(agent_name, {}).get("forbidden", []))
