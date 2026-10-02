"""The committed backend<->frontend contract must match the live OpenAPI schema.

`frontend/src/contracts/backend-contract.generated.json` is the distilled shape
of every response model the frontend parses. If a `*Response` model changes and
the file is not regenerated, this fails — and points at the fix.

    uv run python -m scripts.dump_openapi   # then commit the result

The frontend side (`frontend/src/contracts/backendContract.test.ts`) checks the
zod schemas against the same file.
"""
import json
from pathlib import Path

from scripts.dump_openapi import OUTPUT_PATH, build_contract, render


def test_committed_contract_matches_openapi():
    assert OUTPUT_PATH.exists(), (
        f"{OUTPUT_PATH} is missing — run `uv run python -m scripts.dump_openapi`"
    )

    committed = OUTPUT_PATH.read_text(encoding="utf-8")
    current = render(build_contract())

    assert committed == current, (
        "backend contract is stale.\n"
        "A tracked *Response model changed shape. Regenerate and commit:\n"
        "    uv run python -m scripts.dump_openapi\n"
        "then update frontend/src/contracts/*.ts if a zod schema needs to follow."
    )


def test_contract_file_is_valid_json_with_tracked_components():
    from scripts.dump_openapi import TRACKED_COMPONENTS

    data = json.loads(Path(OUTPUT_PATH).read_text(encoding="utf-8"))
    assert set(data["components"]) == set(TRACKED_COMPONENTS)
    for spec in data["components"].values():
        assert set(spec["required"]).issubset(spec["properties"])
