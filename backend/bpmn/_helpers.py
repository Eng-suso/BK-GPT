"""Leaf helpers shared across the BPMN package: id allocation, traceability
source-refs, and the DeliR documentation payload conventions.
"""

from __future__ import annotations

import json
import re
from html import escape

from backend.bpmn.models import ProcessUnderstandingRef
from backend.process_understanding import ProcessActor, ProcessDecision, ProcessStep


def xml_id(value: str, prefix: str, used: set[str]) -> str:
    """Generate a unique, valid XML identifier from a value string.

    Args:
        value: Source string to convert into an XML ID.
        prefix: Prefix to use if the value is empty or starts with an invalid character.
        used: Set of already-used IDs to ensure uniqueness.

    Returns:
        A unique XML-safe identifier, registered in the `used` set.
    """
    candidate = re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_")
    if not candidate or not re.match(r"^[A-Za-z_]", candidate):
        candidate = f"{prefix}_{candidate}" if candidate else prefix
    base = candidate[:70]
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base}_{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def source_ref(field: str, item_id: str | None, label: str | None = None) -> ProcessUnderstandingRef:
    """Create a ProcessUnderstandingRef for traceability.

    Args:
        field: The source field name in the ProcessUnderstanding model.
        item_id: Optional identifier for the source item.
        label: Optional human-readable label for the source item.

    Returns:
        A ProcessUnderstandingRef instance.
    """
    return ProcessUnderstandingRef(field=field, id=item_id, label=label)


def source_ref_id(field: str, item_id: str | None) -> str:
    """Generate a traceability reference ID string.

    Args:
        field: The source field name.
        item_id: Optional identifier for the item.

    Returns:
        A string in the format "field:item_id".
    """
    return f"{field}:{item_id or '_'}"


def source_ref_from_id(value: str) -> ProcessUnderstandingRef:
    """Parse a traceability reference ID string into a ProcessUnderstandingRef.

    Args:
        value: A string in the format "field:item_id".

    Returns:
        A ProcessUnderstandingRef instance extracted from the ID.
    """
    field, _, item_id = value.partition(":")
    return ProcessUnderstandingRef(field=field or "unknown", id=item_id or None)


def json_documentation(kind: str, payload: dict) -> str:
    """Generate a structured documentation string with JSON payload.

    Args:
        kind: The type of element being documented (e.g., "step", "decision").
        payload: Dictionary containing the element's metadata.

    Returns:
        A formatted documentation string with JSON representation.
    """
    return f"DeliR {kind} context:\n" + json.dumps(payload, ensure_ascii=False, sort_keys=True)


def documentation_xml(text: str, indent: str) -> list[str]:
    """Generate XML documentation element lines.

    Args:
        text: The documentation text to include.
        indent: Indentation prefix for the XML lines.

    Returns:
        A list of XML-formatted documentation lines.
    """
    return [
        f"{indent}<bpmn:documentation>",
        f"{indent}  {escape(text)}",
        f"{indent}</bpmn:documentation>",
    ]


def element_documentation(documentation: str | None, source_refs: list[str]) -> str:
    """Combine user documentation with traceability metadata.

    Args:
        documentation: Optional human-readable documentation text.
        source_refs: List of traceability reference IDs.

    Returns:
        A combined documentation string with both content and traceability.
    """
    payload = {"source_refs": source_refs}
    parts = []
    if documentation:
        parts.append(documentation)
    if source_refs:
        parts.append("DeliR traceability:\n" + json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return "\n\n".join(parts)


def actor_label(actors: list[ProcessActor], actor_ids: list[str]) -> str | None:
    """Generate a comma-separated label string for a list of actor IDs.

    Args:
        actors: List of ProcessActor instances.
        actor_ids: List of actor IDs to look up.

    Returns:
        A comma-separated string of actor labels, or None if no matches found.
    """
    by_id = {actor.id: actor.label for actor in actors}
    labels = [by_id[actor_id] for actor_id in actor_ids if actor_id in by_id]
    return ", ".join(labels) if labels else None


def step_documentation(step: ProcessStep, actors: list[ProcessActor]) -> str:
    """Generate documentation payload for a process step.

    Args:
        step: The ProcessStep to document.
        actors: List of all actors for label resolution.

    Returns:
        A JSON-formatted documentation string with step metadata.
    """
    return json_documentation(
        "step",
        {
            "description": step.description,
            "actors": actor_label(actors, step.actor_ids),
            "inputs": step.inputs,
            "outputs": step.outputs,
            "source_evidence": step.source_evidence,
        },
    )


def decision_documentation(decision: ProcessDecision) -> str:
    """Generate documentation payload for a process decision.

    Args:
        decision: The ProcessDecision to document.

    Returns:
        A JSON-formatted documentation string with decision metadata.
    """
    return json_documentation(
        "decision",
        {
            "question": decision.question,
            "outcomes": decision.outcomes,
            "source_evidence": decision.source_evidence,
        },
    )


def unique_texts(values: list[str]) -> list[str]:
    """Deduplicate and normalize a list of text values.

    Args:
        values: List of strings to deduplicate.

    Returns:
        A list of unique, normalized (whitespace-collapsed) non-empty strings.
    """
    result: list[str] = []
    for value in values:
        clean = " ".join(str(value or "").split())
        if clean and clean not in result:
            result.append(clean)
    return result
