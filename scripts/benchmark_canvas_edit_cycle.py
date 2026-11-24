r"""Paired live benchmark of a whole canvas edit cycle: XML context vs compact map.

Run from the repository root (any OpenAI-compatible endpoint; the key is read
from an environment variable and never printed):

    uv run python -m scripts.benchmark_canvas_edit_cycle --repeat 1 \
        --model gemini-3.5-flash-lite \
        --base-url https://generativelanguage.googleapis.com/v1beta/openai/

Each run gives the model one consultant request, the canvas in one
representation and two tools backed by the production edit functions
(`update_element`, `delete_element`). The loop ends at the first applied edit
or after ``MAX_CALLS`` calls. Applied edits go through the L5 integrity check;
a run is correct only when the resulting semantic tree equals the one produced
by the expected operation. Tokens are the provider-reported usage of every
call in the run. Scope: tool loop and edit functions, not the LangGraph
runtime, the database write or the browser.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import statistics
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from backend.bpmn.canvas_layout import apply_enterprise_layout
from backend.bpmn.compact_canvas_map import compact_canvas_map
from backend.bpmn.compact_representation import semantic_tree
from backend.bpmn.edit_integrity import assert_local_edit_integrity
from backend.workspace_services.bpmn_canvas_edit import delete_bpmn_element, update_bpmn_element

ROOT = Path(__file__).resolve().parents[1]
MAX_CALLS = 3
STOP_ERRORS = {"RateLimitError", "AuthenticationError", "PermissionDeniedError", "NotFoundError"}


@dataclass(frozen=True)
class Case:
    fixture: str
    request: str
    operation: str
    target: str
    name: str | None = None


CASES = (
    Case("omg_valid_minimal.bpmn",
         "Rinomina il passaggio immediatamente dopo 'Request received' in 'Check request'.",
         "update_element", "Review", "Check request"),
    Case("purchase_layout.bpmn",
         "Elimina il passaggio in cui si raccoglie la firma del direttore.",
         "delete_element", "Director_Sign"),
    Case("multibranch_layout.bpmn",
         "Rinomina l'attivita' del ramo alternativo che parte da 'Scelta del percorso 1' "
         "in 'Controlla il caso alternativo'.",
         "update_element", "Task_1_B", "Controlla il caso alternativo"),
)

POLICY = (
    "Sei l'agente che modifica il canvas BPMN del consulente. Applica esattamente la "
    "modifica richiesta con un solo tool, usando gli ID della rappresentazione fornita. "
    "Non inventare ID. Se la richiesta non identifica un solo elemento, non chiamare tool "
    "e spiega perche'."
)


@tool
def update_element(element_id: str, name: str) -> str:
    """Rename the BPMN element with this exact ID."""
    return "applied"


@tool
def delete_element(element_id: str) -> str:
    """Delete the BPMN element with this exact ID and the flows that touch it."""
    return "applied"


def _fixture_xml(case: Case) -> str:
    return apply_enterprise_layout((ROOT / "tests" / "fixtures" / case.fixture).read_text(encoding="utf-8"))


def apply_operation(xml: str, operation: str, element_id: str, name: str | None) -> tuple[str, dict]:
    """Apply one tool call with the production function and the L5 check."""
    if operation == "update_element":
        updated, change = update_bpmn_element(xml, element_id, name=name)
    elif operation == "delete_element":
        updated, change = delete_bpmn_element(xml, element_id)
    else:
        raise ValueError(f"Operazione non prevista: {operation}")
    assert_local_edit_integrity(before_xml=xml, after_xml=updated, operation=operation,
                                change=change, element_id=element_id)
    return updated, change


def expected_semantics(case: Case) -> tuple:
    xml = _fixture_xml(case)
    return semantic_tree(apply_operation(xml, case.operation, case.target, case.name)[0])


def usage_of(response) -> dict:
    usage = getattr(response, "usage_metadata", None) or {}
    return {
        "input": usage.get("input_tokens") or 0,
        "output": usage.get("output_tokens") or 0,
        "cached_input": (usage.get("input_token_details") or {}).get("cache_read") or 0,
        "reported": bool(usage),
    }


def run_case(llm, case: Case, representation: str) -> dict:
    xml = _fixture_xml(case)
    body = xml if representation == "xml" else compact_canvas_map(xml)
    messages = [SystemMessage(content=POLICY), HumanMessage(
        content=f"Richiesta del consulente: {case.request}\n\nCanvas ({representation}):\n{body}"
    )]
    bound = llm.bind_tools([update_element, delete_element])
    row = {"fixture": case.fixture, "representation": representation, "calls": 0,
           "tool_calls": 0, "input_tokens": 0, "output_tokens": 0, "cached_input_tokens": 0,
           "usage_reported_calls": 0, "applied": None, "correct": False, "integrity_ok": None}
    started = perf_counter()
    try:
        for _ in range(MAX_CALLS):
            response = bound.invoke(messages)
            row["calls"] += 1
            usage = usage_of(response)
            row["input_tokens"] += usage["input"]
            row["output_tokens"] += usage["output"]
            row["cached_input_tokens"] += usage["cached_input"]
            row["usage_reported_calls"] += int(usage["reported"])
            calls = getattr(response, "tool_calls", None) or []
            if not calls:
                break
            messages.append(response)
            call = calls[0]
            row["tool_calls"] += len(calls)
            args = call.get("args") or {}
            row["applied"] = {"operation": call["name"], **args}
            try:
                result, _change = apply_operation(xml, call["name"], str(args.get("element_id")),
                                                  args.get("name"))
            except ValueError as exc:
                # A wrong ID or a refused edit goes back to the model, as in the product.
                row["integrity_ok"] = "alterato dati BPMN" not in str(exc)
                messages.append(ToolMessage(content=f"Errore: {exc}", tool_call_id=call["id"]))
                continue
            row["integrity_ok"] = True
            row["correct"] = semantic_tree(result) == expected_semantics(case)
            break
    except Exception as exc:  # provider failures are reported, never scored as wrong answers
        row["error_type"] = type(exc).__name__
    row["latency_ms"] = round((perf_counter() - started) * 1000, 2)
    return row


def summarize(rows: list[dict]) -> dict:
    groups = {}
    for representation in ("xml", "map"):
        cases = [row for row in rows if row["representation"] == representation]
        completed = [row for row in cases if "error_type" not in row]
        tokens = [row["input_tokens"] + row["output_tokens"] for row in completed
                  if row["usage_reported_calls"] == row["calls"] and row["calls"]]
        groups[representation] = {
            "attempts": len(cases),
            "completed": len(completed),
            "provider_errors": len(cases) - len(completed),
            "correct": sum(row["correct"] for row in completed),
            "integrity_violations": sum(row["integrity_ok"] is False for row in completed),
            "median_calls": statistics.median(row["calls"] for row in completed) if completed else None,
            "median_total_tokens": statistics.median(tokens) if tokens else None,
            "median_latency_ms": round(statistics.median(row["latency_ms"] for row in completed), 2)
            if completed else None,
        }
    xml, compact = groups["xml"]["median_total_tokens"], groups["map"]["median_total_tokens"]
    groups["token_reduction_median"] = round(1 - compact / xml, 4) if xml and compact else None
    return groups


def build_client(model: str, base_url: str | None, api_key: str):
    from langchain_openai import ChatOpenAI

    kwargs = {"model": model, "api_key": api_key, "temperature": 0, "max_retries": 0,
              "timeout": 120, "max_tokens": 512}
    if base_url:
        kwargs["base_url"] = base_url
    return ChatOpenAI(**kwargs)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--model", default=os.environ.get("DELIR_TEST_LLM_MODEL"))
    parser.add_argument("--base-url", default=os.environ.get("DELIR_TEST_LLM_BASE_URL"))
    parser.add_argument("--api-key-env", default="DELIR_TEST_LLM_API_KEY")
    args = parser.parse_args()
    api_key = os.environ.get(args.api_key_env)
    if args.repeat < 1 or not args.model or not api_key:
        parser.error("servono --repeat >= 1, --model e la chiave in --api-key-env")
    llm = build_client(args.model, args.base_url, api_key)
    order = [(case, representation, repeat) for repeat in range(args.repeat)
             for case in CASES for representation in ("xml", "map")]
    random.Random(20261124).shuffle(order)
    rows = []
    for case, representation, repeat in order:
        row = {"repeat": repeat, **run_case(llm, case, representation)}
        rows.append(row)
        if row.get("error_type") in STOP_ERRORS:
            break
    status = "complete" if len(rows) == len(order) else "incomplete_provider_error"
    print(json.dumps({"benchmark": "canvas_edit_cycle_v1", "model": args.model,
                      "scope": "tool loop with production edit functions and L5 check; "
                               "no LangGraph runtime, database or browser",
                      "status": status, "summary": summarize(rows), "cases": rows},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
