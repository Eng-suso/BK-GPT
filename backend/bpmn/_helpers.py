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


def xml_id_preview(value: str) -> str:
    candidate = re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_")
    return candidate[:70]


def source_ref(field: str, item_id: str | None, label: str | None = None) -> ProcessUnderstandingRef:
    return ProcessUnderstandingRef(field=field, id=item_id, label=label)


def source_ref_id(field: str, item_id: str | None) -> str:
    return f"{field}:{item_id or '_'}"


def source_ref_from_id(value: str) -> ProcessUnderstandingRef:
    field, _, item_id = value.partition(":")
    return ProcessUnderstandingRef(field=field or "unknown", id=item_id or None)


def json_documentation(kind: str, payload: dict) -> str:
    return f"DeliR {kind} context:\n" + json.dumps(payload, ensure_ascii=False, sort_keys=True)


def documentation_xml(text: str, indent: str) -> list[str]:
    return [
        f"{indent}<bpmn:documentation>",
        f"{indent}  {escape(text)}",
        f"{indent}</bpmn:documentation>",
    ]


def element_documentation(documentation: str | None, source_refs: list[str]) -> str:
    payload = {"source_refs": source_refs}
    parts = []
    if documentation:
        parts.append(documentation)
    if source_refs:
        parts.append("DeliR traceability:\n" + json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return "\n\n".join(parts)


def actor_label(actors: list[ProcessActor], actor_ids: list[str]) -> str | None:
    by_id = {actor.id: actor.label for actor in actors}
    labels = [by_id[actor_id] for actor_id in actor_ids if actor_id in by_id]
    return ", ".join(labels) if labels else None


def step_documentation(step: ProcessStep, actors: list[ProcessActor]) -> str:
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
    return json_documentation(
        "decision",
        {
            "question": decision.question,
            "outcomes": decision.outcomes,
            "source_evidence": decision.source_evidence,
        },
    )


def unique_texts(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        clean = " ".join(str(value or "").split())
        if clean and clean not in result:
            result.append(clean)
    return result
