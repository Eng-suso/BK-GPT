from pathlib import Path


def load_markdown_skills(skill_dir: Path) -> str:
    if not skill_dir.exists():
        return ""

    skill_docs = []

    for path in sorted(skill_dir.glob("*.md")):
        content = path.read_text(encoding="utf-8").strip()
        if content:
            skill_docs.append(f"## Local Skill: {path.stem}\n\n{content}")

    if not skill_docs:
        return ""

    return (
        "Local procedural memory for this agent. Use these instructions as "
        "scope-specific operating method for the current turn.\n\n"
        + "\n\n---\n\n".join(skill_docs)
    )


def tool_prompt_block(tools: list) -> str:
    lines = []

    for tool in tools:
        name = getattr(tool, "name", tool.__class__.__name__)
        description = str(getattr(tool, "description", "") or "").strip()
        lines.append(f"- `{name}`: {description or 'No description provided.'}")

    return "Available tools and intended use:\n" + "\n".join(lines)
