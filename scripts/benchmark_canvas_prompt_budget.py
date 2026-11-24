r"""Where the tokens of one Patch/Edit call go: deterministic, no model.

Builds the exact input the production Patch/Edit agent sends on its first
call (``build_context_messages`` with or without ``_compact_canvas_patch``,
the subgraph contract, the consultant request, the tool schemas) and counts
each part with the o200k tokenizer used by the context budget. Run:

    uv run python -m scripts.benchmark_canvas_prompt_budget

The live runtime probe (``benchmark_canvas_runtime``) showed that most of a
call is fixed prompt, not canvas; this report says which part.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ("omg_valid_minimal.bpmn", "purchase_layout.bpmn", "multibranch_layout.bpmn",
            "omg_issue_list.bpmn")
REQUEST = "Rinomina il passaggio di verifica in 'Controllo finale'."


def prompt_parts(xml: str, *, compact: bool) -> dict[str, int]:
    from langchain_core.utils.function_calling import convert_to_openai_tool

    from backend.agent import build_context_messages, load_procedural_memory
    from backend.agents.context_budget import count_tokens
    from backend.graphs.canvas_edit.subgraphs.patch_edit import patch_edit_tools
    from backend.graphs.canvas_edit.subgraphs.patch_edit.graph import PATCH_EDIT_SUBGRAPH_CONTRACT
    from langchain_core.messages import HumanMessage

    state = {"messages": [HumanMessage(content=REQUEST)], "scope_type": "canvas",
             "bpmn_model_id": "benchmark-model", "effective_bpmn_xml": xml, "current_bpmn_xml": xml,
             "_compact_canvas_patch": compact}
    messages = build_context_messages(state)
    procedural = load_procedural_memory()
    system = [str(message.content) for message in messages if message.type == "system"]
    scope = next(text for text in system if text != procedural)
    other_system = [text for text in system if text not in {procedural, scope}]
    conversation = [str(message.content) for message in messages if message.type != "system"]
    schemas = json.dumps([convert_to_openai_tool(item) for item in patch_edit_tools], ensure_ascii=False)
    return {
        "procedural_memory": count_tokens(procedural),
        "scope_prompt": count_tokens(scope),
        "other_system": sum(count_tokens(text) for text in other_system),
        "subgraph_contract": count_tokens(PATCH_EDIT_SUBGRAPH_CONTRACT),
        "conversation": sum(count_tokens(text) for text in conversation),
        "tool_schemas": count_tokens(schemas),
    }


def report() -> dict:
    from backend.bpmn.canvas_layout import apply_enterprise_layout

    rows = []
    for fixture in FIXTURES:
        xml = apply_enterprise_layout((ROOT / "tests" / "fixtures" / fixture).read_text(encoding="utf-8"))
        for representation in ("xml", "map"):
            parts = prompt_parts(xml, compact=representation == "map")
            rows.append({"fixture": fixture, "representation": representation,
                         "total": sum(parts.values()), **parts})
    summary = {}
    for representation in ("xml", "map"):
        selected = [row for row in rows if row["representation"] == representation]
        summary[representation] = {key: statistics.median(row[key] for row in selected)
                                   for key in selected[0] if key not in {"fixture", "representation"}}
    fixed = ("procedural_memory", "subgraph_contract", "tool_schemas")
    summary["fixed_share_of_map_call"] = round(
        sum(summary["map"][key] for key in fixed) / summary["map"]["total"], 4)
    summary["first_call_reduction_median"] = round(statistics.median(
        1 - map_row["total"] / xml_row["total"]
        for xml_row, map_row in zip(rows[0::2], rows[1::2], strict=True)), 4)
    return {"benchmark": "canvas_patch_prompt_budget_v1", "tokenizer": "o200k",
            "summary": summary, "rows": rows}


if __name__ == "__main__":
    print(json.dumps(report(), ensure_ascii=False, indent=2))
