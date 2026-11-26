"""Local, provider-free baseline for a single canvas rename.

Run from the repository root with ``uv run python -m scripts.benchmark_canvas_patch``.
The measurements cover Python work and scope prompt size. They do not include
database, browser, network, or LLM time.
"""

from __future__ import annotations

import argparse
import json
import statistics
import xml.etree.ElementTree as ET
from pathlib import Path
from time import perf_counter

from backend.agents.context_budget import _encoding, count_tokens
from backend.agents.primary_scope import build_scope_system_prompt
from backend.bpmn.canvas_layout import apply_enterprise_layout
from backend.workspace_services.bpmn_canvas_edit import (
    list_bpmn_elements,
    update_bpmn_element,
    validate_bpmn_layout,
    validate_bpmn_xml,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURES = (
    ROOT / "tests/fixtures/purchase_layout.bpmn",
    ROOT / "tests/fixtures/multibranch_layout.bpmn",
    ROOT / "tests/fixtures/omg_issue_list.bpmn",
)
BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
BPMNDI_NS = "http://www.omg.org/spec/BPMN/20100524/DI"


def _structure(xml: str) -> tuple[set[str], set[tuple[str, str, str]]]:
    root = ET.fromstring(xml)
    ids = {
        element.attrib["id"]
        for element in root.iter()
        if element.tag.startswith("{" + BPMN_NS + "}") and element.attrib.get("id")
    }
    flows = {
        (element.attrib["id"], element.attrib["sourceRef"], element.attrib["targetRef"])
        for element in root.iter("{" + BPMN_NS + "}sequenceFlow")
    }
    return ids, flows


def _semantic_tree(xml: str, renamed_id: str) -> tuple:
    """Compare every semantic attribute and child except the requested new name."""
    root = ET.fromstring(xml)

    def visit(element: ET.Element) -> tuple:
        attrs = dict(element.attrib)
        if attrs.get("id") == renamed_id:
            attrs.pop("name", None)
        children = tuple(
            visit(child)
            for child in element
            if not child.tag.startswith("{" + BPMNDI_NS + "}")
        )
        return element.tag, tuple(sorted(attrs.items())), (element.text or "").strip(), children

    return visit(root)


def _median_ms(values: list[float]) -> float:
    return round(statistics.median(values), 2)


def benchmark(fixture: Path, repeat: int) -> dict:
    source_xml = fixture.read_text(encoding="utf-8")
    started = perf_counter()
    xml = apply_enterprise_layout(source_xml)
    initial_layout_ms = round((perf_counter() - started) * 1000, 2)
    editable = next(
        (element for element in list_bpmn_elements(xml) if element["type"] in {"task", "userTask", "serviceTask", "manualTask"}),
        None,
    )
    if editable is None:
        raise ValueError(f"No task to rename in {fixture}")

    state = {
        "scope_type": "canvas",
        "chat_mode": "edit",
        "current_bpmn_xml": xml,
        "effective_bpmn_xml": xml,
        "effective_bpmn_xml_source": "live_canvas",
    }
    full_prompt_tokens = count_tokens(build_scope_system_prompt(state))
    patch_prompt_tokens = count_tokens(build_scope_system_prompt(state, compact_canvas_patch=True))

    patch_times: list[float] = []
    layout_times: list[float] = []
    validation_times: list[float] = []
    original_structure = _structure(xml)
    original_semantics = _semantic_tree(xml, editable["id"])
    for _ in range(repeat):
        started = perf_counter()
        patched, _change = update_bpmn_element(xml, editable["id"], name="Benchmark Rename")
        patch_times.append((perf_counter() - started) * 1000)

        started = perf_counter()
        laid_out = apply_enterprise_layout(patched)
        layout_times.append((perf_counter() - started) * 1000)

        started = perf_counter()
        technical = validate_bpmn_xml(laid_out)
        visual = validate_bpmn_layout(laid_out)
        validation_times.append((perf_counter() - started) * 1000)
        if not technical["valid"] or not visual["valid"]:
            raise AssertionError(f"Rename failed validation in {fixture}")
        if _structure(laid_out) != original_structure:
            raise AssertionError(f"Rename changed BPMN IDs or sequence flows in {fixture}")
        if _semantic_tree(laid_out, editable["id"]) != original_semantics:
            raise AssertionError(f"Rename changed untouched BPMN semantics in {fixture}")

    return {
        "fixture": fixture.name,
        "source_characters": len(source_xml),
        "normalized_characters": len(xml),
        "initial_layout_ms": initial_layout_ms,
        "flow_nodes": technical["counts"]["flow_nodes"],
        "sequence_flows": technical["counts"]["sequence_flows"],
        "scope_tokens_full": full_prompt_tokens,
        "scope_tokens_patch": patch_prompt_tokens,
        "patch_ms_median": _median_ms(patch_times),
        "layout_ms_median": _median_ms(layout_times),
        "validation_ms_median": _median_ms(validation_times),
        "structure_preserved": True,
        "untouched_semantics_preserved": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixtures", nargs="*", type=Path, default=DEFAULT_FIXTURES)
    parser.add_argument("--repeat", type=int, default=5)
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("--repeat must be at least 1")
    report = {
        "benchmark": "canvas_local_rename",
        "repeat": args.repeat,
        "tokenizer": "o200k_base" if _encoding() is not None else "utf8_byte_upper_bound",
        "scope": "Python patch, layout, validation, and scope prompt only",
        "cases": [benchmark(path, args.repeat) for path in args.fixtures],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
