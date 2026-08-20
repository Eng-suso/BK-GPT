CONSULTING_SKILLS_MANIFEST = {
    "consult_macro": {
        "required": [
            "consult_macro_orchestration",
            "workspace_triage",
            "delegation_policy",
            "consultant_memory_governance",
            "consulting_delivery",
        ],
        "optional": [
            "strategic_planning",
            "sales_method",
            "content_style",
        ],
        "forbidden": [
            "process_discovery",
            "process_modeling",
            "process_analysis",
            "canvas_bpmn_editing",
            "bpmn_validation",
        ],
    },
    "home_subgraph": {
        "required": [
            "home_dashboard_governance",
            "workspace_status_synthesis",
        ],
        "optional": [],
        "forbidden": [
            "client_record_management",
            "initial_workspace_setup",
            "process_modeling",
            "canvas_bpmn_editing",
        ],
    },
    "clients_subgraph": {
        "required": [
            "client_record_management",
            "workspace_data_hygiene",
        ],
        "optional": [],
        "forbidden": [
            "initial_workspace_setup",
            "process_modeling",
            "canvas_bpmn_editing",
        ],
    },
    "setup_subgraph": {
        "required": [
            "initial_workspace_setup",
            "workspace_data_hygiene",
        ],
        "optional": [],
        "forbidden": [
            "process_discovery",
            "process_modeling",
            "canvas_bpmn_editing",
        ],
    },
}


def required_skills_for(agent_name: str) -> list[str]:
    return list(CONSULTING_SKILLS_MANIFEST.get(agent_name, {}).get("required", []))


def forbidden_skills_for(agent_name: str) -> list[str]:
    return list(CONSULTING_SKILLS_MANIFEST.get(agent_name, {}).get("forbidden", []))
