"""Project specialist tool results into typed ProcessState fields.

The specialist subgraphs are plain chat+tool loops: ToolNode appends each tool
result as a ToolMessage and nothing else writes state. Every typed accumulator on
ProcessState (contradictions, gaps, claims, readiness, coverage) therefore stayed
empty for the whole run, which left the gates reading them unable to ever fire -
`no_critical_contradictions` blocked nothing - and left the engineering loop's
progress signature blind to three of the eleven terms it counts.

This node closes that gap. It reads the ToolMessages produced since it last ran
and projects the ones it recognises into typed state, so the runtime can verify
judgments the agent has already recorded.

Kept import-light on purpose: no langchain, no graph imports, so the projection
can be unit-tested without the agent stack.
"""

import json
from typing import Any


# Tool result entity types this node knows how to project, mapped to what they
# mean for state. Anything else is left in the transcript untouched.
PROJECTED_ENTITY_TYPES = frozenset(
    {
        "process_contradiction",
        "process_contradiction_resolution",
        "process_gap",
        "process_claims",
        "process_discovery_readiness",
        "process_evidence_coverage",
        "process_understanding_readiness",
    }
)


def _message_field(message: Any, field: str) -> Any:
    if isinstance(message, dict):
        return message.get(field)
    return getattr(message, field, None)


def _is_tool_message(message: Any) -> bool:
    return _message_field(message, "type") == "tool"


def parse_tool_result(content: Any) -> dict | None:
    """Parse one `enterprise_tool_result` payload back into a dict.

    The wire format is `f"{action}\\n{json}"` (see toolsets.common), so the first
    line is dropped before decoding. Anything that is not a well-formed result is
    ignored rather than raised on: a specialist turn must not fail because one
    tool wrote something unexpected.
    """
    if not isinstance(content, str):
        return None

    _, separator, body = content.partition("\n")
    if not separator:
        return None

    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return None

    return parsed if isinstance(parsed, dict) else None


def project_specialist_results(state: dict) -> dict:
    """Project tool results produced since the last pass into typed state.

    Runs after each specialist subgraph and before the engineering-loop
    evaluation, so the loop's progress signature sees the claims, gaps and
    contradictions the pass actually produced.
    """
    messages = state.get("messages") or []
    already_projected = int(state.get("projected_message_count") or 0)

    contradictions: list[dict] = []
    process_gaps: list[dict] = []
    process_claims: list[dict] = []
    discovery_readiness: dict | None = None
    evidence_coverage: dict | None = None
    minimum_readiness_score: int | None = None

    for message in messages[already_projected:]:
        if not _is_tool_message(message):
            continue

        result = parse_tool_result(_message_field(message, "content"))
        if not result:
            continue

        entity_type = result.get("entity_type")
        if entity_type not in PROJECTED_ENTITY_TYPES:
            continue

        payload = result.get("payload")
        if not isinstance(payload, dict):
            continue

        if entity_type in {"process_contradiction", "process_contradiction_resolution"}:
            # Both kinds land in the same list: the gate folds them by title so a
            # later resolution can clear an earlier contradiction (and a re-raise
            # can un-clear it again).
            contradictions.append(payload)
        elif entity_type == "process_gap":
            process_gaps.append(payload)
        elif entity_type == "process_claims":
            process_claims.extend(
                claim for claim in payload.get("claims") or [] if isinstance(claim, dict)
            )
        elif entity_type == "process_discovery_readiness":
            discovery_readiness = payload
        elif entity_type == "process_evidence_coverage":
            evidence_coverage = payload
        elif entity_type == "process_understanding_readiness":
            score = payload.get("minimum_readiness_score")
            if isinstance(score, int) and not isinstance(score, bool) and 1 <= score <= 10:
                minimum_readiness_score = score

    # The high-water mark is what keeps the append-reducer fields from
    # re-collecting the same tool results on every pass of the engineering loop.
    update: dict[str, Any] = {"projected_message_count": len(messages)}

    if contradictions:
        update["contradictions"] = contradictions
    if process_gaps:
        update["process_gaps"] = process_gaps
    if process_claims:
        update["process_claims"] = process_claims
    if discovery_readiness is not None:
        update["discovery_readiness"] = discovery_readiness
    if evidence_coverage is not None:
        update["evidence_coverage"] = evidence_coverage
    if minimum_readiness_score is not None:
        update["minimum_readiness_score"] = minimum_readiness_score

    return update
