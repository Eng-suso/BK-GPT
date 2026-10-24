import re
from dataclasses import dataclass
from pathlib import Path




PROCEDURAL_DIR = Path(__file__).resolve().parent
SKILLS_DIR = PROCEDURAL_DIR / "skills"

MAX_SKILLS_PER_TURN = 4


@dataclass(frozen=True)
class ProceduralSkill:
    name: str
    description: str
    path: Path


def message_content_to_text(content) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
        return " ".join(parts)

    return str(content or "")


def recent_user_text(messages: list, limit: int = 4) -> str:
    user_messages = []

    for message in reversed(messages):
        role = getattr(message, "type", None) or getattr(message, "role", "")
        if role in {"human", "user"}:
            user_messages.append(message_content_to_text(getattr(message, "content", "")))

        if len(user_messages) >= limit:
            break

    return "\n\n".join(reversed(user_messages)).strip()


def parse_frontmatter(markdown: str) -> tuple[dict[str, str], str]:
    if not markdown.startswith("---"):
        return {}, markdown

    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", markdown, re.DOTALL)

    if not match:
        return {}, markdown

    metadata: dict[str, str] = {}

    for line in match.group(1).splitlines():
        if ":" not in line:
            continue

        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"').strip("'")

    return metadata, match.group(2)


def normalize_skill_name(name: str) -> str:
    return name.removesuffix(".md").replace("-", "_").strip().lower()


def load_skill_registry() -> list[ProceduralSkill]:
    skills: list[ProceduralSkill] = []

    if not SKILLS_DIR.exists():
        return skills

    for path in sorted(SKILLS_DIR.glob("*.md")):
        markdown = path.read_text(encoding="utf-8").strip()
        metadata, _ = parse_frontmatter(markdown)
        name = normalize_skill_name(metadata.get("name") or path.stem)
        description = metadata.get("description", "").strip()

        if not description:
            continue

        skills.append(
            ProceduralSkill(
                name=name,
                description=description,
                path=path,
            )
        )

    return skills


def normalize_selected_skill_names(raw_skills, valid_names: set[str]) -> list[str]:
    if not isinstance(raw_skills, list):
        return []

    selected = []

    for raw_name in raw_skills:
        skill_name = normalize_skill_name(str(raw_name))
        if skill_name in valid_names and skill_name not in selected:
            selected.append(skill_name)

        if len(selected) >= MAX_SKILLS_PER_TURN:
            break

    return selected


def load_skill_markdown(skill_name: str) -> str:
    normalized_name = normalize_skill_name(skill_name)

    for skill in load_skill_registry():
        if skill.name == normalized_name:
            return skill.path.read_text(encoding="utf-8").strip()

    return ""


def build_skill_context_from_names(skill_names: list[str]) -> str:
    registry = load_skill_registry()
    valid_names = {skill.name for skill in registry}
    selected_skills = normalize_selected_skill_names(skill_names, valid_names)

    if not selected_skills:
        return ""

    loaded_skills = []

    for skill_name in selected_skills:
        skill_content = load_skill_markdown(skill_name)
        if skill_content:
            loaded_skills.append(
                f"## Active Skill: {skill_name}.md\n\n{skill_content}"
            )

    if not loaded_skills:
        return ""

    return (
        "Active procedural skills for this turn.\n"
        "Use these Markdown instructions as the consultant's operating method for the current task. "
        "Do not mention skill loading unless the user asks.\n\n"
        + "\n\n---\n\n".join(loaded_skills)
    )
