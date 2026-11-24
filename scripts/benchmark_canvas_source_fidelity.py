r"""Paired L4 probe: does a compact representation still let a model check sources?

Run from the repository root (any OpenAI-compatible endpoint; the key is read
from an environment variable and never printed):

    uv run python -m scripts.benchmark_canvas_source_fidelity --repeat 1 \
        --model gemini-3.5-flash-lite \
        --base-url https://generativelanguage.googleapis.com/v1beta/openai/

Each case pairs a source description with a model that, by construction,
misses one step the source states and contains one step the source never
mentions. The same model, prompt and source are given the BPMN as full XML,
as DeliR DSL v1 (autonomous, reversible) or as the navigation map, in a
seeded random order. The rubric counts the planted omissions and unsupported
claims the model finds, and every other finding as a false positive (a
hallucinated discrepancy). Synthetic cases only: this is a probe of
the representation, not a measure of extraction quality on customer data.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import statistics
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from backend.bpmn.compact_canvas_map import compact_canvas_map
from backend.bpmn.compact_representation import encode_delir_dsl
from scripts.benchmark_canvas_edit_cycle import STOP_ERRORS, _PACE, paced_invoke
from scripts.live_llm_support import RETRY_STATS, build_client, wilson_interval
from backend.workspace_services.bpmn_canvas_edit import (
    add_bpmn_element,
    connect_bpmn_elements,
    delete_bpmn_element,
)

ROOT = Path(__file__).resolve().parents[1]
REPRESENTATIONS = ("xml", "dsl_v1", "map")


@dataclass(frozen=True)
class Case:
    name: str
    source: str
    fixture: str
    drop: str
    invent: str
    invent_after: str
    invent_before: str
    missing_label: str


CASES = (
    Case(
        "purchase",
        "L'ufficio tecnico apre la richiesta di acquisto, allegando il documento di richiesta. "
        "Acquisti verifica l'autorizzazione e valuta se l'importo supera 5000 euro: sopra soglia "
        "raccoglie la firma del direttore, altrimenti procede. Poi crea e invia l'ordine e il "
        "processo termina con l'ordine inviato. Nei casi urgenti la manutenzione chiama "
        "subito il fornitore.",
        "purchase_layout.bpmn",
        drop="Verify",
        invent="Invia sondaggio di soddisfazione al fornitore",
        invent_after="Create_Order",
        invent_before="End",
        missing_label="Verifica autorizzazione",
    ),
    Case(
        "minimal",
        "When a request is received, the team reviews it and then files it in the register; "
        "once filed, the request counts as reviewed.",
        "omg_valid_minimal.bpmn",
        drop="",
        invent="Call the customer for confirmation",
        invent_after="Review",
        invent_before="End",
        missing_label="File the request in the register",
    ),
    Case(
        "purchase_urgent",
        "L'ufficio tecnico apre la richiesta di acquisto. Acquisti verifica l'autorizzazione e, "
        "se l'importo supera 5000 euro, raccoglie la firma del direttore; poi crea e invia "
        "l'ordine. Quando il guasto e' urgente, la manutenzione chiama subito il fornitore "
        "senza aspettare l'ordine.",
        "purchase_layout.bpmn",
        drop="Urgent_Call",
        invent="Archivia la richiesta nel gestionale",
        invent_after="Create_Order",
        invent_before="End",
        missing_label="Chiama fornitore urgente",
    ),
    Case(
        "multibranch",
        "Dopo l'inizio si sceglie il percorso 0: verifica della pratica principale 0 oppure "
        "controllo dell'alternativa 0, poi si prosegue. Si sceglie quindi il percorso 1: "
        "verifica della pratica principale 1 oppure controllo dell'alternativa 1, poi si "
        "prosegue e il processo e' completato.",
        "multibranch_layout.bpmn",
        drop="Task_1_A",
        invent="Invia notifica al cliente",
        invent_after="Join_1",
        invent_before="End",
        missing_label="Verifica pratica principale 1",
    ),
    Case(
        "issue_list",
        "While the working group is active, every Friday at 6 PM Pacific Time someone checks "
        "the status of the working group. If it is still active, the current issue list is "
        "sent and the cycle waits for the next Friday; otherwise the process ends.",
        "omg_issue_list.bpmn",
        drop="Send",
        invent="Publish the minutes on the website",
        invent_after="Check",
        invent_before="Active",
        missing_label="Send current issue list",
    ),
)

POLICY = (
    "Confronta il processo descritto dalla fonte con il modello BPMN fornito. Elenca i "
    "passaggi che la fonte afferma ma il modello non contiene, e i passaggi del modello che "
    "la fonte non sostiene. Usa le etichette come appaiono. Rispondi solo con JSON "
    '{"missing_from_model": ["..."], "unsupported_in_model": ["..."]}.'
)


def build_model(case: Case) -> str:
    xml = (ROOT / "tests" / "fixtures" / case.fixture).read_text(encoding="utf-8")
    if case.drop:
        xml, _ = delete_bpmn_element(xml, case.drop)
    xml, change = add_bpmn_element(xml, "task", case.invent)
    xml, _ = connect_bpmn_elements(xml, case.invent_after, change["id"])
    xml, _ = connect_bpmn_elements(xml, change["id"], case.invent_before)
    return xml


def represent(xml: str, representation: str) -> str:
    if representation == "xml":
        return xml
    if representation == "dsl_v1":
        return encode_delir_dsl(xml)
    return compact_canvas_map(xml)


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return " ".join(re.findall(r"[a-z0-9]+", text))


def matches(found: str, expected: str) -> bool:
    found_n, expected_n = _normalize(found), _normalize(expected)
    if not found_n or not expected_n:
        return False
    if expected_n in found_n or found_n in expected_n:
        return True
    return SequenceMatcher(None, found_n, expected_n).ratio() >= 0.75


def parse_answer(raw: str) -> dict:
    text = raw.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.S)
    value = json.loads(fenced.group(1) if fenced else text)
    if not isinstance(value, dict) or set(value) != {"missing_from_model", "unsupported_in_model"}:
        raise ValueError("Risposta non conforme allo schema JSON")
    for key in value:
        if not isinstance(value[key], list) or not all(isinstance(item, str) for item in value[key]):
            raise ValueError(f"{key} deve essere una lista di stringhe")
    return value


def score(answer: dict, case: Case) -> dict:
    missing = answer["missing_from_model"]
    unsupported = answer["unsupported_in_model"]
    found_missing = any(matches(item, case.missing_label) for item in missing)
    found_unsupported = any(matches(item, case.invent) for item in unsupported)
    false_positives = (
        sum(not matches(item, case.missing_label) for item in missing)
        + sum(not matches(item, case.invent) for item in unsupported)
    )
    return {"found_missing": found_missing, "found_unsupported": found_unsupported,
            "false_positives": false_positives}


def run_case(llm, case: Case, representation: str) -> dict:
    body = represent(build_model(case), representation)
    messages = [SystemMessage(content=POLICY), HumanMessage(
        content=f"Fonte:\n{case.source}\n\nModello BPMN ({representation}):\n{body}"
    )]
    row = {"case": case.name, "representation": representation}
    retries_before = RETRY_STATS["retries"]
    try:
        response = paced_invoke(llm, messages)
    except Exception as exc:  # provider failures are not wrong answers
        row.update(error_type=type(exc).__name__, latency_ms=round(_PACE["last_latency_ms"], 2),
                   retries=RETRY_STATS["retries"] - retries_before)
        return row
    row["retries"] = RETRY_STATS["retries"] - retries_before
    row["latency_ms"] = round(_PACE["last_latency_ms"], 2)
    usage = getattr(response, "usage_metadata", None) or {}
    row["input_tokens"] = usage.get("input_tokens")
    row["output_tokens"] = usage.get("output_tokens")
    # Synthetic cases only: the raw answer stays in the report for audit.
    row["answer"] = str(response.content)
    try:
        row.update(parsed=True, **score(parse_answer(row["answer"]), case))
    except (ValueError, json.JSONDecodeError):
        row.update(parsed=False, found_missing=False, found_unsupported=False, false_positives=0)
    return row


def summarize(rows: list[dict]) -> dict:
    groups = {}
    for representation in REPRESENTATIONS:
        cases = [row for row in rows if row["representation"] == representation]
        completed = [row for row in cases if "error_type" not in row]
        inputs = [row["input_tokens"] for row in completed if isinstance(row.get("input_tokens"), int)]
        found_missing = sum(row["found_missing"] for row in completed)
        found_unsupported = sum(row["found_unsupported"] for row in completed)
        groups[representation] = {
            "missing_recall_ci95": wilson_interval(found_missing, len(completed)),
            "unsupported_recall_ci95": wilson_interval(found_unsupported, len(completed)),
            "rate_limit_retries": sum(row.get("retries", 0) for row in cases),
            "attempts": len(cases),
            "completed": len(completed),
            "provider_errors": len(cases) - len(completed),
            "parse_failures": sum(row["parsed"] is False for row in completed),
            "missing_recall": round(sum(row["found_missing"] for row in completed) / len(completed), 3)
            if completed else None,
            "unsupported_recall": round(sum(row["found_unsupported"] for row in completed) / len(completed), 3)
            if completed else None,
            "false_positives": sum(row["false_positives"] for row in completed),
            "median_input_tokens": statistics.median(inputs) if inputs else None,
        }
    return groups


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--model", default=os.environ.get("DELIR_TEST_LLM_MODEL"))
    parser.add_argument("--base-url", default=os.environ.get("DELIR_TEST_LLM_BASE_URL"))
    parser.add_argument("--api-key-env", default="DELIR_TEST_LLM_API_KEY")
    parser.add_argument("--min-interval", type=float, default=0.0)
    args = parser.parse_args()
    api_key = (os.environ.get(args.api_key_env) or "").strip()
    if args.repeat < 1 or not args.model or not api_key:
        parser.error("servono --repeat >= 1, --model e la chiave in --api-key-env")
    _PACE["interval"] = args.min_interval
    llm = build_client(args.model, args.base_url, api_key)
    order = [(case, representation, repeat) for repeat in range(args.repeat)
             for case in CASES for representation in REPRESENTATIONS]
    random.Random(20261124).shuffle(order)
    rows = []
    for case, representation, repeat in order:
        row = {"repeat": repeat, **run_case(llm, case, representation)}
        rows.append(row)
        if row.get("error_type") in STOP_ERRORS:
            break
    status = "complete" if len(rows) == len(order) else "incomplete_provider_error"
    print(json.dumps({"benchmark": "canvas_source_fidelity_l4_v2", "model": args.model,
                      "scope": "planted omissions and unsupported steps, synthetic cases",
                      "status": status, "summary": summarize(rows), "cases": rows},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
