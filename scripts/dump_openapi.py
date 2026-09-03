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
    """Extract the component name from an OpenAPI reference string.
    
    Parameters:
    	ref (str): An OpenAPI reference containing a component path.
    
    Returns:
    	str: The final path segment of the reference.
    """
    return ref.rsplit("/", 1)[-1]


def type_token(schema: dict[str, Any]) -> str:
    """
    Convert an OpenAPI property schema into a compact comparable type token.
    
    Parameters:
        schema (dict[str, Any]): OpenAPI property schema to convert.
    
    Returns:
        str: Component name, nullable token, array token, primitive type, or ``"unknown"`` for unsupported schemas.
    """
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
    """
    Create a deterministic reduced representation of an OpenAPI component.
    
    Parameters:
    	component (dict[str, Any]): The OpenAPI component schema to reduce.
    
    Returns:
    	dict[str, Any]: A mapping containing sorted required field names and sorted
    		property names with their compact type tokens.
    """
    properties = component.get("properties", {})
    return {
        "required": sorted(component.get("required", [])),
        "properties": {
            name: type_token(prop) for name, prop in sorted(properties.items())
        },
    }


def build_contract() -> dict[str, Any]:
    """
    Build the reduced frontend contract from the application's OpenAPI schemas.
    
    Returns:
    	dict[str, Any]: The generated contract containing the generator marker and tracked component definitions.
    
    Raises:
    	SystemExit: If any tracked component is missing from the OpenAPI schema.
    """
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
    """
    Serialize a contract as indented JSON with a trailing newline.
    
    Parameters:
    	contract (dict[str, Any]): The contract to serialize.
    
    Returns:
    	str: The UTF-8-compatible JSON representation of the contract.
    """
    return json.dumps(contract, indent=2, ensure_ascii=False) + "\n"


def main() -> None:
    """
    Generate the frontend contract file from the FastAPI OpenAPI schema and report its path.
    """
    OUTPUT_PATH.write_text(render(build_contract()), encoding="utf-8")
    print(f"wrote {OUTPUT_PATH.relative_to(Path.cwd())}")


if __name__ == "__main__":
    main()
