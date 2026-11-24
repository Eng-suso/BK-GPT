r"""Paired live benchmark inside the production canvas runtime: full XML vs map.

Unlike ``benchmark_canvas_edit_cycle`` (a minimal tool loop), this runs the
production Patch/Edit subgraph: the same procedural memory, scope prompt
(``build_scope_system_prompt``), subgraph contract, tool schemas, ToolNode and
tools that write through ``update_bpmn_model``. The only switch is
``compact_canvas_patch``: ``True`` is the path this PR ships (navigation map
inline), ``False`` the previous one (full canvas XML in the prompt).

It writes BPMN models, so it refuses to start unless ``WORKSPACE_DATABASE_URL``
points at a test stack and ``--i-know-this-writes`` is given. Each run gets its
own tenant. Correct = the BPMN read back from the database has the same
semantics as the expected edit (or no new version, for the ambiguous case).

    uv run python -m scripts.benchmark_canvas_runtime --i-know-this-writes \
        --model openai/gpt-oss-120b --base-url https://api.groq.com/openai/v1
"""

from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys
import uuid
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
DEV_PORTS = {"55300", "5432"}


def _assert_test_database() -> None:
    url = os.environ.get("WORKSPACE_DATABASE_URL", "")
    port = url.rsplit("@", 1)[-1].split("/", 1)[0].rsplit(":", 1)[-1] if "@" in url else ""
    if not url or port in DEV_PORTS:
        sys.exit("WORKSPACE_DATABASE_URL deve puntare a uno stack di test (non sviluppo).")


class _Meter:
    """LangChain callback: provider tokens and call time, minus rate-limit waits."""

    def __new__(cls):
        from langchain_core.callbacks import BaseCallbackHandler

        from scripts.live_llm_support import RETRY_STATS

        class Meter(BaseCallbackHandler):
            def __init__(self) -> None:
                self.calls: list[dict] = []
                self._open: dict = {}

            def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):
                self._open[run_id] = (perf_counter(), RETRY_STATS["waited_s"])

            def on_llm_end(self, response, *, run_id, **kwargs):
                started, waited = self._open.pop(run_id, (perf_counter(), RETRY_STATS["waited_s"]))
                message = response.generations[0][0].message
                usage = getattr(message, "usage_metadata", None) or {}
                elapsed = perf_counter() - started - (RETRY_STATS["waited_s"] - waited)
                self.calls.append({
                    "latency_ms": round(max(elapsed, 0.0) * 1000, 2),
                    "input": usage.get("input_tokens"),
                    "output": usage.get("output_tokens"),
                    "cached_input": (usage.get("input_token_details") or {}).get("cache_read") or 0,
                })

        return Meter()


def _semantics(xml: str):
    # The projection the L5 gate uses: derived incoming/outgoing refs ignored.
    from backend.bpmn.edit_integrity import _semantic_projection

    return _semantic_projection(xml)


def run_case(graph_by_representation: dict, case, representation: str) -> dict:
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    from backend import workspace_database as wd
    from backend.agents.run_context import bind_turn_writes
    from backend.bpmn.canvas_layout import apply_enterprise_layout
    from backend.security import reset_current_tenant_id, set_current_tenant_id
    from scripts.benchmark_canvas_edit_cycle import apply_operation
    from scripts.live_llm_support import RETRY_STATS

    row = {"fixture": case.fixture, "operation": case.operation, "representation": representation}
    token = set_current_tenant_id(f"t-bench-rt-{uuid.uuid4().hex[:10]}")
    retries_before = RETRY_STATS["retries"]
    meter = _Meter()
    try:
        client = wd.create_client(name="Benchmark runtime canvas")
        project = wd.create_project(client_id=client["id"], name="Benchmark")
        process = wd.create_process(project_id=project["id"], name=f"Benchmark {uuid.uuid4().hex[:6]}")
        model_id = process["bpmn_model_id"]
        source = apply_enterprise_layout((ROOT / "tests" / "fixtures" / case.fixture).read_text(encoding="utf-8"))
        saved = wd.update_bpmn_model(model_id, source, source="canvas_benchmark_seed")
        expected_xml = saved["xml"] if case.operation == "none" else apply_operation(
            saved["xml"], case.operation, case.target, case.name)[0]
        state = {
            "messages": [HumanMessage(content=case.request)],
            "scope_type": "canvas",
            "bpmn_model_id": model_id,
            "process_id": process["id"],
            "project_id": project["id"],
            "effective_bpmn_xml": saved["xml"],
            "current_bpmn_xml": saved["xml"],
        }
        try:
            with bind_turn_writes({model_id: saved["version_id"]}):
                result = graph_by_representation[representation].invoke(
                    state, config={"callbacks": [meter], "recursion_limit": 24},
                )
        except Exception as exc:  # provider or runtime failure: reported, not scored
            row["error_type"] = type(exc).__name__
            row["error"] = str(exc)[:300]
            result = None
        final = wd.get_bpmn_model(model_id)["xml"]
        versions = len(wd.list_bpmn_versions(model_id)) - 1
        messages = (result or {}).get("messages", [])[1:]
        tool_results = [message for message in messages if isinstance(message, ToolMessage)]
        row.update(
            versions_written=versions,
            tool_calls=sum(len(getattr(message, "tool_calls", None) or [])
                           for message in messages if isinstance(message, AIMessage)),
            tool_names=[call["name"] for message in messages if isinstance(message, AIMessage)
                        for call in (getattr(message, "tool_calls", None) or [])],
            # Which canvas operation each call asked for: a "map" or "inspect" read
            # while the map is already in the prompt is a call the prompt did not save.
            tool_operations=[(call.get("args") or {}).get("operation") for message in messages
                             if isinstance(message, AIMessage)
                             for call in (getattr(message, "tool_calls", None) or [])],
            tool_errors=sum("non e' andato a buon fine" in str(message.content)
                            or "Modifica non salvata" in str(message.content) for message in tool_results),
            integrity_violations=sum("alterato dati BPMN" in str(message.content) for message in tool_results),
            correct=(versions == 0) if case.operation == "none"
            else (versions >= 1 and _semantics(final) == _semantics(expected_xml)),
            reply=str(messages[-1].content)[:400] if messages else "",
        )
    finally:
        reset_current_tenant_id(token)
    calls = meter.calls
    row.update(
        calls=len(calls),
        input_tokens=sum(call["input"] or 0 for call in calls),
        output_tokens=sum(call["output"] or 0 for call in calls),
        cached_input_tokens=sum(call["cached_input"] for call in calls),
        usage_reported_calls=sum(call["input"] is not None for call in calls),
        latency_ms=round(sum(call["latency_ms"] for call in calls), 2),
        retries=RETRY_STATS["retries"] - retries_before,
    )
    return row


def summarize(rows: list[dict]) -> dict:
    from scripts.live_llm_support import wilson_interval

    groups = {}
    for representation in ("xml", "map"):
        cases = [row for row in rows if row["representation"] == representation]
        completed = [row for row in cases if "error_type" not in row]
        tokens = [row["input_tokens"] + row["output_tokens"] for row in completed
                  if row["calls"] and row["usage_reported_calls"] == row["calls"]]
        correct = sum(row["correct"] for row in completed)
        groups[representation] = {
            "attempts": len(cases),
            "completed": len(completed),
            "errors": len(cases) - len(completed),
            "correct": correct,
            "correct_rate_ci95": wilson_interval(correct, len(completed)),
            "integrity_violations": sum(row["integrity_violations"] for row in completed),
            "median_calls": statistics.median(row["calls"] for row in completed) if completed else None,
            "median_total_tokens": statistics.median(tokens) if tokens else None,
            "median_latency_ms": round(statistics.median(row["latency_ms"] for row in completed), 2)
            if completed else None,
            "rate_limit_retries": sum(row["retries"] for row in cases),
        }
    # Paired reduction: only cases completed in both representations.
    by_key = {(row["fixture"], row["operation"], row.get("repeat", 0), row["representation"]): row
              for row in rows if "error_type" not in row and row["calls"]}
    ratios = []
    for (fixture, operation, repeat, representation), row in by_key.items():
        if representation != "map":
            continue
        xml = by_key.get((fixture, operation, repeat, "xml"))
        if xml and xml["input_tokens"] + xml["output_tokens"]:
            ratios.append(1 - (row["input_tokens"] + row["output_tokens"])
                          / (xml["input_tokens"] + xml["output_tokens"]))
    groups["paired_token_reduction_median"] = round(statistics.median(ratios), 4) if ratios else None
    groups["paired_cases"] = len(ratios)
    return groups


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--model", default=os.environ.get("DELIR_TEST_LLM_MODEL"))
    parser.add_argument("--base-url", default=os.environ.get("DELIR_TEST_LLM_BASE_URL"))
    parser.add_argument("--api-key-env", default="DELIR_TEST_LLM_API_KEY")
    parser.add_argument("--i-know-this-writes", action="store_true")
    parser.add_argument("--max-cases", type=int, default=None, help="solo i primi N casi (giro di prova)")
    args = parser.parse_args()
    api_key = (os.environ.get(args.api_key_env) or "").strip()
    if args.repeat < 1 or not args.model or not api_key or not args.i_know_this_writes:
        parser.error("servono --i-know-this-writes, --repeat >= 1, --model e la chiave")
    _assert_test_database()

    from backend.agent import build_context_messages
    from backend.graphs.canvas_edit.subgraphs.patch_edit import build_patch_edit_subgraph, patch_edit_tools
    from scripts.benchmark_canvas_edit_cycle import CASES, STOP_ERRORS
    from scripts.live_llm_support import build_client

    llm = build_client(args.model, args.base_url, api_key, max_tokens=2048).bind_tools(patch_edit_tools)
    graphs = {
        representation: build_patch_edit_subgraph(
            llm, lambda state, compact=(representation == "map"): build_context_messages(
                {**state, "_compact_canvas_patch": compact}),
        )
        for representation in ("xml", "map")
    }
    rng = random.Random(20261124)
    order = []
    for repeat in range(args.repeat):
        cases = list(CASES)
        rng.shuffle(cases)
        cases = cases[:args.max_cases] if args.max_cases else cases
        for case in cases:
            pair = ["xml", "map"]
            rng.shuffle(pair)
            order.extend((case, representation, repeat) for representation in pair)
    rows = []
    for case, representation, repeat in order:
        row = {"repeat": repeat, **run_case(graphs, case, representation)}
        rows.append(row)
        print(json.dumps({key: row.get(key) for key in (
            "fixture", "operation", "representation", "correct", "calls",
            "input_tokens", "error_type")}), file=sys.stderr, flush=True)
        if row.get("error_type") in STOP_ERRORS:
            break
    status = "complete" if len(rows) == len(order) else "incomplete_provider_error"
    print(json.dumps({"benchmark": "canvas_runtime_patch_edit_v1", "model": args.model,
                      "scope": "production patch-edit subgraph, prompts, tool schemas and DB writes "
                               "on a test stack; no router, browser or completion loop",
                      "status": status, "summary": summarize(rows), "cases": rows},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
