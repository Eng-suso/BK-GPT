"""Distil the FastAPI OpenAPI schema into a small backend<->frontend contract.

Writes `frontend/src/contracts/backend-contract.generated.json`: for every
response model the frontend consumes, the required field list and a one-token
type per property. `tests/test_api_contract.py` regenerates this in memory and
fails if the committed file is stale; `frontend/src/contracts/*.contract.test.ts`
checks the zod schemas against it.

    uv run python -m scripts.dump_openapi

Re-run and commit the result whenever a `*Response` model changes shape.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Response components the frontend parses (see frontend/src/contracts/).
TRACKED_COMPONENTS = [
    "ClientResponse",
    "ProjectResponse",
    "ProjectProcessResponse",
    "ProjectSourceResponse",
    "ProjectDecisionResponse",
    "BpmnModelResponse",
    "BpmnVersionResponse",
    "RestoreBpmnVersionResponse",
    "BpmnReviewResponse",
    "ApproveBpmnReviewResponse",
    "CreateSessionResponse",
    "ChatSessionSummary",
    "ChatSessionDetail",
    "ChatMessageRecord",
    "ChatResponse",
    "TranscriptionResponse",
]

OUTPUT_PATH = (
    Path(__file__).resolve().parent.parent
    / "frontend"
    / "src"
    / "contracts"
    / "backend-contract.generated.json"
)


def _ref_name(ref: str) -> str:
    return ref.rsplit("/", 1)[-1]


def type_token(schema: dict[str, Any]) -> str:
    """Collapse an OpenAPI property schema to a single comparable token."""
    if "$ref" in schema:
        return _ref_name(schema["$ref"])

    any_of = schema.get("anyOf")
    if any_of:
        non_null = [s for s in any_of if s.get("type") != "null"]
        nullable = len(non_null) != len(any_of)
        inner = type_token(non_null[0]) if non_null else "unknown"
        return f"{inner}?" if nullable else inner

    kind = schema.get("type")
    if kind == "array":
        return f"{type_token(schema.get('items', {}))}[]"
    if kind in {"string", "integer", "number", "boolean", "object", "null"}:
        return kind
    return "unknown"


def distil_component(component: dict[str, Any]) -> dict[str, Any]:
    properties = component.get("properties", {})
    return {
        "required": sorted(component.get("required", [])),
        "properties": {
            name: type_token(prop) for name, prop in sorted(properties.items())
        },
    }


def build_contract() -> dict[str, Any]:
    from backend.app import app

    schemas = app.openapi()["components"]["schemas"]
    missing = [name for name in TRACKED_COMPONENTS if name not in schemas]
    if missing:
        raise SystemExit(f"OpenAPI is missing tracked components: {missing}")

    return {
        "_generated_by": "uv run python -m scripts.dump_openapi",
        "components": {
            name: distil_component(schemas[name]) for name in TRACKED_COMPONENTS
        },
    }


def render(contract: dict[str, Any]) -> str:
    return json.dumps(contract, indent=2, ensure_ascii=False) + "\n"


def main() -> None:
    OUTPUT_PATH.write_text(render(build_contract()), encoding="utf-8")
    print(f"wrote {OUTPUT_PATH.relative_to(Path.cwd())}")


if __name__ == "__main__":
    main()
