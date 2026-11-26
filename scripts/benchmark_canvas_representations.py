"""Compare real BPMN fixtures with experimental compact representations.

TOK is run as an external, pinned CLI via uvx; no TOK code enters DeliR.
BPCF has no BPMN XML importer, so fixture conversion is explicitly unmeasured.
No language is eligible for a lossless canvas path without semantic round-trip.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from time import perf_counter

from backend.agents.context_budget import _encoding, count_tokens
from backend.agents.primary_scope import build_scope_system_prompt
from backend.bpmn.omg_conformance import omg_xsd_issues
from backend.bpmn.compact_canvas_map import compact_canvas_map
from backend.workspace_services.bpmn_canvas_edit import validate_bpmn_xml
from backend.bpmn.compact_representation import (
    decode_delir_dsl, decode_delir_dsl_v2, encode_delir_dsl, encode_delir_dsl_v2, semantic_tree,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURES = tuple(
    ROOT / "tests/fixtures" / name
    for name in ("purchase_layout.bpmn", "multibranch_layout.bpmn", "omg_issue_list.bpmn")
)
BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"


def _omg_xsd_valid(xml: str) -> bool:
    return not omg_xsd_issues(xml)


def _elements(xml: str) -> dict[str, tuple]:
    root = ET.fromstring(xml)
    return {
        element.attrib["id"]: (
            element.tag,
            element.attrib.get("name", ""),
            element.attrib.get("sourceRef", ""),
            element.attrib.get("targetRef", ""),
        )
        for element in root.iter()
        if element.tag.startswith("{" + BPMN_NS + "}") and "id" in element.attrib
    }


def _tok_case(xml: str, fixture_name: str, directory: Path) -> dict:
    input_path = directory / fixture_name
    tok_path = directory / (fixture_name + ".tok")
    roundtrip_path = directory / (fixture_name + ".roundtrip.bpmn")
    input_path.write_text(xml, encoding="utf-8")
    command = ["uvx", "--from", "tok-lang==1.0.4", "tok"]
    started = perf_counter()
    imported = subprocess.run(
        [*command, "import", str(input_path), "-o", str(tok_path), "--no-layout"],
        capture_output=True, text=True, check=False, timeout=60,
    )
    import_ms = round((perf_counter() - started) * 1000, 2)
    if imported.returncode != 0 or not tok_path.exists():
        return {"status": "import_failed", "diagnostics": imported.stderr.strip()}
    started = perf_counter()
    exported = subprocess.run(
        [*command, "bpmn", str(tok_path), "-o", str(roundtrip_path), "--no-layout"],
        capture_output=True, text=True, check=False, timeout=60,
    )
    export_ms = round((perf_counter() - started) * 1000, 2)
    text = tok_path.read_text(encoding="utf-8")
    if exported.returncode != 0 or not roundtrip_path.exists():
        return {"status": "export_failed", "tokens": count_tokens(text),
                "diagnostics": [line for line in (*imported.stderr.splitlines(),
                                                   *exported.stderr.splitlines(),
                                                   *exported.stdout.splitlines()) if line.strip()]}
    rebuilt = roundtrip_path.read_text(encoding="utf-8")
    before = _elements(xml)
    after = _elements(rebuilt)
    missing = sorted(before.keys() - after.keys())
    changed = sorted(key for key in before.keys() & after.keys() if before[key] != after[key])
    return {
        "status": "measured",
        "tokens": count_tokens(text),
        "characters": len(text),
        "import_ms": import_ms,
        "export_ms": export_ms,
        "semantic_roundtrip_exact": semantic_tree(xml) == semantic_tree(rebuilt),
        "missing_original_ids": missing,
        "changed_original_ids": changed,
        "diagnostics": [line for line in imported.stderr.splitlines() if line.strip()],
    }


def benchmark_xml(xml: str, name: str, directory: Path, include_tok: bool) -> dict:
    state = {
        "scope_type": "canvas",
        "chat_mode": "edit",
        "current_bpmn_xml": xml,
        "effective_bpmn_xml": xml,
        "effective_bpmn_xml_source": "live_canvas",
    }
    full_scope_tokens = count_tokens(build_scope_system_prompt(state))
    patch_scope_tokens = count_tokens(build_scope_system_prompt(state, compact_canvas_patch=True))
    result = {
        "fixture": name,
        "bpmn_xml": {"tokens": count_tokens(xml), "characters": len(xml),
                     "omg_xsd_valid": _omg_xsd_valid(xml)},
        "canvas_scope_prompt": {
            "full_tokens": full_scope_tokens,
            "local_patch_tokens": patch_scope_tokens,
            "reduction": round(1 - patch_scope_tokens / full_scope_tokens, 4),
        },
        "canvas_navigation_map": {
            "tokens": count_tokens(compact_canvas_map(xml)),
            "scope": "read-only ID/label/edge index; not a round-trip representation",
        },
        "bpcf_full": {"status": "not_measured", "reason":
                      "Official BPCF repository has no BPMN XML importer; manual transcription would not be a controlled same-model comparison."},
    }
    started = perf_counter()
    try:
        dsl = encode_delir_dsl(xml)
    except ValueError as exc:
        result["delir_dsl_v1"] = {"status": "unsupported", "reason": str(exc)}
        if include_tok:
            result["tok_1_0_4"] = _tok_case(xml, name, directory)
        return result
    encoded_ms = round((perf_counter() - started) * 1000, 2)
    started = perf_counter()
    rebuilt = decode_delir_dsl(dsl)
    decoded_ms = round((perf_counter() - started) * 1000, 2)
    exact = semantic_tree(xml) == semantic_tree(rebuilt)
    if not exact:
        raise AssertionError(f"DeliR DSL lost semantic XML in {name}")
    if not validate_bpmn_xml(rebuilt)["valid"]:
        raise AssertionError(f"DeliR DSL produced invalid BPMN in {name}")
    result["semantic_xml_minified"] = {"tokens": count_tokens(rebuilt), "characters": len(rebuilt)}
    result["delir_dsl_v1"] = {"status": "measured", "tokens": count_tokens(dsl), "characters": len(dsl),
                              "encode_ms": encoded_ms, "decode_ms": decoded_ms,
                              "semantic_roundtrip_exact": exact, "local_bpmn_valid": True,
                              "omg_xsd_valid": _omg_xsd_valid(rebuilt)}
    try:
        dsl_v2 = encode_delir_dsl_v2(xml)
        rebuilt_v2 = decode_delir_dsl_v2(dsl_v2)
    except ValueError as exc:
        result["delir_dsl_v2"] = {"status": "unsupported", "reason": str(exc)}
    else:
        exact_v2 = semantic_tree(xml) == semantic_tree(rebuilt_v2)
        if not exact_v2:
            raise AssertionError(f"DeliR DSL v2 lost semantic XML in {name}")
        result["delir_dsl_v2"] = {
            "status": "measured", "tokens": count_tokens(dsl_v2), "characters": len(dsl_v2),
            "semantic_roundtrip_exact": True, "omg_xsd_valid": _omg_xsd_valid(rebuilt_v2),
        }
    if include_tok:
        result["tok_1_0_4"] = _tok_case(xml, name, directory)
    return result


def benchmark(fixture: Path, directory: Path, include_tok: bool) -> dict:
    return benchmark_xml(fixture.read_text(encoding="utf-8"), fixture.name, directory, include_tok)


def _summary(cases: list[dict]) -> dict:
    measured = [case for case in cases if case["delir_dsl_v1"]["status"] == "measured"]
    tok_cases = [case["tok_1_0_4"] for case in cases if "tok_1_0_4" in case]
    reductions = [
        1 - case["delir_dsl_v1"]["tokens"] / case["semantic_xml_minified"]["tokens"]
        for case in measured if case["semantic_xml_minified"]["tokens"]
    ]
    prompt_reductions = [case["canvas_scope_prompt"]["reduction"] for case in cases]
    v2 = [case for case in cases if case.get("delir_dsl_v2", {}).get("status") == "measured"]
    v2_reductions = [1 - case["delir_dsl_v2"]["tokens"] / case["bpmn_xml"]["tokens"]
                     for case in v2 if case["bpmn_xml"]["tokens"]]
    map_reductions = [1 - case["canvas_navigation_map"]["tokens"] / case["bpmn_xml"]["tokens"]
                      for case in cases if case["bpmn_xml"]["tokens"]]
    sidecar_summary = {}
    for key in ("pmo_mermaid", "pmo_json_branches"):
        ratios = [
            1 - case[key]["tokens"] / case["bpmn_xml"]["tokens"]
            for case in cases if key in case and case["bpmn_xml"]["tokens"]
        ]
        sidecar_summary[key] = {
            "available": len(ratios),
            "median_reduction_vs_full_xml": round(statistics.median(ratios), 4) if ratios else None,
            "semantic_roundtrip": "unverified",
        }
    return {
        "total": len(cases),
        "omg_xsd_valid_sources": sum(case["bpmn_xml"]["omg_xsd_valid"] for case in cases),
        "delir_supported": len(measured),
        "delir_exact_roundtrips": sum(case["delir_dsl_v1"]["semantic_roundtrip_exact"] for case in measured),
        "delir_median_reduction_vs_semantic_xml": round(statistics.median(reductions), 4) if reductions else None,
        "delir_v2_supported": len(v2),
        "delir_v2_exact_roundtrips": sum(case["delir_dsl_v2"]["semantic_roundtrip_exact"] for case in v2),
        "delir_v2_median_reduction_vs_full_xml": round(statistics.median(v2_reductions), 4)
        if v2_reductions else None,
        "delir_v2_cases_at_least_85_percent": sum(value >= 0.85 for value in v2_reductions),
        "canvas_map_median_reduction_vs_full_xml": round(statistics.median(map_reductions), 4)
        if map_reductions else None,
        "canvas_map_cases_at_least_85_percent": sum(value >= 0.85 for value in map_reductions),
        "local_patch_scope_median_reduction": round(statistics.median(prompt_reductions), 4)
        if prompt_reductions else None,
        "local_patch_scope_cases_at_least_90_percent": sum(value >= 0.9 for value in prompt_reductions),
        "tok_attempted": len(tok_cases),
        "tok_exact_roundtrips": sum(case.get("semantic_roundtrip_exact") is True for case in tok_cases)
        if tok_cases else None,
        "published_pmo_sidecars": sidecar_summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixtures", nargs="*", type=Path, default=DEFAULT_FIXTURES)
    parser.add_argument("--tok", action="store_true", help="Run official TOK CLI through uvx")
    parser.add_argument("--pmo-zip", type=Path, help="PMo Dataset 1.0.0 ZIP; reads bpmn/*.bpmn without extraction")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="delir-representation-") as temp:
        if args.pmo_zip:
            with zipfile.ZipFile(args.pmo_zip) as archive:
                names = sorted(name for name in archive.namelist()
                               if name.startswith("bpmn/") and name.endswith(".bpmn")
                               and len(Path(name).parts) == 2)
                available = set(archive.namelist())
                cases = []
                for name in names:
                    stem = Path(name).stem
                    case = benchmark_xml(archive.read(name).decode("utf-8"), Path(name).name,
                                         Path(temp), args.tok)
                    for key, member in (("pmo_mermaid", f"mermaid/{stem}.mmd"),
                                        ("pmo_json_branches", f"json_branches/{stem}.json")):
                        if member in available:
                            body = archive.read(member).decode("utf-8")
                            case[key] = {"tokens": count_tokens(body), "characters": len(body),
                                         "semantic_roundtrip": "unverified"}
                    cases.append(case)
        else:
            cases = [benchmark(path, Path(temp), args.tok) for path in args.fixtures]
    print(json.dumps({"benchmark": "canvas_representations_v1", "tokenizer":
                      "o200k_base" if _encoding() is not None else "utf8_byte_upper_bound",
                      "summary": _summary(cases), "cases": cases}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
