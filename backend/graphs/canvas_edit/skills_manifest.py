CANVAS_REQUIRED_SKILLS = {
    "canvas_macro": [
        "canvas_macro_orchestration",
    ],
    "patch_edit_subgraph": [
        "canvas_patch_edit",
    ],
    "construction_subgraph": [
        "canvas_construction",
    ],
    "layout_subgraph": [
        "canvas_layout",
    ],
    "validation_subgraph": [
        "canvas_validation",
    ],
}


def required_skills_for(owner: str) -> list[str]:
    return CANVAS_REQUIRED_SKILLS.get(owner, [])
