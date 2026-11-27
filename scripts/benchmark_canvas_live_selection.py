r"""Paired live LLM probe: choose one exact canvas edit target from XML or map.

Run from the repository root:
    .venv\Scripts\python.exe -m scripts.benchmark_canvas_live_selection --repeat 1

The six requests use public/synthetic fixtures. This measures one model call,
including provider-reported tokens and latency. It does not measure the whole
canvas tool loop or claim semantic fidelity of a generated process.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from langchain_core.messages import HumanMessage, SystemMessage

from backend.agent import normalize_model_name
from backend.bpmn.compact_canvas_map import compact_canvas_map
from backend.bpmn.canvas_layout import apply_enterprise_layout
from backend.llm import DeliRChatOpenAI
from backend.settings import settings

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Case:
    fixture: str
    request: str
    expected_id: str


CASES = (
    Case("omg_valid_minimal.bpmn",
         "Rinomina il passaggio immediatamente dopo 'Request received' in 'Check request'.",
         "Review"),
    Case("purchase_layout.bpmn",
         "Rinomina l'attivita' svolta da Manutenzione in 'Chiama subito il fornitore'.",
         "Urgent_Call"),
    Case("multibranch_layout.bpmn",
         "Rinomina l'attivita' del ramo alternativo che parte da 'Scelta del percorso 1' "
         "in 'Controlla il caso alternativo'.", "Task_1_B"),
)

POLICY = (
    "Seleziona il singolo elemento BPMN da rinominare. Usa solo la rappresentazione "
    "fornita e restituisci esattamente JSON {\"element_id\": \"ID\"}. "
    "Se non puoi stabilirlo univocamente, restituisci {\"element_id\": null}. "
    "Non inventare un ID e non modificare il modello."
)


def parse_target(raw: str) -> str | None:
    value = json.loads(raw)
    if not isinstance(value, dict) or set(value) != {"element_id"}:
        raise ValueError("Risposta non conforme allo schema JSON")
    target = value["element_id"]
    if target is not None and not isinstance(target, str):
        raise ValueError("element_id deve essere una stringa o null")
    return target


def _client(model: str) -> DeliRChatOpenAI:
    kwargs = {
        "model": model,
        "api_key": settings.openai_api_key,
        "temperature": settings.model_temperature,
        "max_tokens": 128,
        "timeout": settings.model_timeout_seconds,
        "max_retries": 1,
        "streaming": False,
        "reasoning_effort": "none",
        "langsmith_provider": settings.langsmith_provider,
        "langsmith_model_name": model,
    }
    if settings.openai_base_url:
        kwargs["base_url"] = settings.openai_base_url
    return DeliRChatOpenAI(**kwargs)


def _usage(response) -> dict | None:
    usage = getattr(response, "usage_metadata", None)
    if not isinstance(usage, dict):
        return None
    return {
        "input": usage.get("input_tokens"),
        "output": usage.get("output_tokens"),
        "total": usage.get("total_tokens"),
        "cached_input": (usage.get("input_token_details") or {}).get("cache_read", 0),
    }


def _run_one(llm: DeliRChatOpenAI, case: Case, representation: str) -> dict:
    xml = apply_enterprise_layout((ROOT / "tests" / "fixtures" / case.fixture).read_text(encoding="utf-8"))
    body = xml if representation == "xml" else compact_canvas_map(xml)
    messages = [SystemMessage(content=POLICY), HumanMessage(
        content=f"Richiesta: {case.request}\n\nRappresentazione {representation}:\n{body}"
    )]
    started = perf_counter()
    try:
        response = llm.invoke(messages)
        latency_ms = round((perf_counter() - started) * 1000, 2)
        raw = str(response.content)
        try:
            selected = parse_target(raw)
            parsed = True
        except (ValueError, json.JSONDecodeError):
            selected, parsed = None, False
        return {
            "fixture": case.fixture, "representation": representation,
            "expected_id": case.expected_id, "selected_id": selected,
            "parsed": parsed, "correct": parsed and selected == case.expected_id,
            "latency_ms": latency_ms, "usage": _usage(response),
        }
    except Exception as exc:
        return {
            "fixture": case.fixture, "representation": representation,
            "expected_id": case.expected_id, "selected_id": None,
            "parsed": None, "correct": None,
            "latency_ms": round((perf_counter() - started) * 1000, 2),
            "usage": None, "error_type": type(exc).__name__,
        }


def summarize(rows: list[dict]) -> dict:
    groups = {}
    for representation in ("xml", "map"):
        cases = [row for row in rows if row["representation"] == representation]
        completed = [row for row in cases if "error_type" not in row]
        totals = [row["usage"]["total"] for row in cases
                  if row["usage"] and isinstance(row["usage"]["total"], int)]
        groups[representation] = {
            "attempts": len(cases), "completed": len(completed),
            "provider_errors": len(cases) - len(completed),
            "correct": sum(row["correct"] is True for row in completed),
            "parse_failures": sum(row["parsed"] is False for row in completed),
            "usage_reported": len(totals),
            "median_total_tokens": statistics.median(totals) if totals else None,
            "median_latency_ms": round(statistics.median(row["latency_ms"] for row in cases), 2)
            if cases else None,
        }
    return groups


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--model", default=None)
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("--repeat deve essere >= 1")
    if not settings.openai_api_key:
        parser.error("OPENAI_API_KEY non configurata")
    model = normalize_model_name(args.model)
    llm = _client(model)
    order = [(case, representation, repeat) for repeat in range(args.repeat)
             for case in CASES for representation in ("xml", "map")]
    random.Random(20261124).shuffle(order)
    rows = []
    for case, representation, repeat in order:
        row = {"repeat": repeat, **_run_one(llm, case, representation)}
        rows.append(row)
        if row.get("error_type") in {"RateLimitError", "AuthenticationError", "PermissionDeniedError"}:
            break
    status = "complete" if len(rows) == len(order) else "incomplete_provider_error"
    print(json.dumps({"benchmark": "canvas_live_target_selection_v1", "model": model,
                      "scope": "one LLM call for exact edit target, no tool loop or save",
                      "status": status, "summary": summarize(rows), "cases": rows},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
