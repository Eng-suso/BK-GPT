"""Metriche dei due compiti LLM della simulazione, sul golden set di `tests/golden/simulation/`.

- SIM-23 (what-if): quante modifiche attese il modello trova (recall), quante ne
  aggiunge che la frase non chiedeva (precision: l'errore piu' pericoloso, perche'
  cambia la bozza senza che il consulente l'abbia detto), e se dice quando una
  parte della frase non si traduce.
- SIM-24b (testo per il cliente): quante volte il testo passa `verify` al primo
  colpo (nessuna cifra del modello) e quanti dei KPI certi cita.

Pure: nessuna chiamata al modello. Il run live (`l1_golden/test_simulation_llm_eval.py`)
le usa sulle risposte vere; i test L0 le verificano su risposte scritte a mano.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "simulation"

# Una modifica numerica e' giusta entro il 2%: "il 30% in meno" e' 0.7, non 0.6999 contro 0.7.
TOLERANCE = 0.02


@dataclass(frozen=True)
class WhatIfCase:
    case_id: str
    language: str
    request: dict[str, Any]
    expected: list[dict[str, Any]]
    not_understood: bool


@dataclass(frozen=True)
class NarrativeCase:
    case_id: str
    request: dict[str, Any]
    must_cite: list[str]
    uncertain: list[str]


def load_what_if_cases() -> list[WhatIfCase]:
    data = json.loads((GOLDEN / "what_if.json").read_text(encoding="utf-8"))
    cases = []
    for item in data["cases"]:
        process = data["processes"][item["process"]]
        request = {"sentence": item["sentence"], "activities": process["activities"], "resources": process["resources"]}
        cases.append(WhatIfCase(item["id"], item["language"], request, item["expected"], item["not_understood"]))
    return cases


def load_narrative_cases() -> list[NarrativeCase]:
    data = json.loads((GOLDEN / "narrative.json").read_text(encoding="utf-8"))
    return [NarrativeCase(c["id"], c["request"], c["must_cite"], c["uncertain"]) for c in data["cases"]]


def _target(change: dict[str, Any]) -> tuple[str, str]:
    return change["kind"], change.get("resource_id") or change.get("element_id") or ""


def _close(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return a is b
    return abs(a - b) <= TOLERANCE * max(abs(a), abs(b), 1e-9)


def same_change(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    """Stesso tipo, stesso elemento, stesso valore entro la tolleranza."""
    if _target(expected) != _target(actual):
        return False
    keys = (set(expected) | set(actual)) - {"kind", "resource_id", "element_id"}
    return all(_close(expected.get(key), actual.get(key)) for key in keys)


@dataclass
class WhatIfScore:
    case_id: str
    true_positive: int = 0
    false_positive: int = 0
    false_negative: int = 0
    not_understood_ok: bool = True
    exact: bool = False
    extra: list[dict[str, Any]] = field(default_factory=list)
    missing: list[dict[str, Any]] = field(default_factory=list)


def score_what_if(case: WhatIfCase, changes: list[dict[str, Any]], not_understood: str | None) -> WhatIfScore:
    score = WhatIfScore(case.case_id)
    left = list(changes)
    for expected in case.expected:
        match = next((actual for actual in left if same_change(expected, actual)), None)
        if match is None:
            score.false_negative += 1
            score.missing.append(expected)
        else:
            score.true_positive += 1
            left.remove(match)
    score.false_positive = len(left)
    score.extra = left
    score.not_understood_ok = bool(not_understood) == case.not_understood
    score.exact = score.false_positive == 0 and score.false_negative == 0 and score.not_understood_ok
    return score


def summarize_what_if(scores: list[WhatIfScore]) -> dict[str, float]:
    tp = sum(s.true_positive for s in scores)
    fp = sum(s.false_positive for s in scores)
    fn = sum(s.false_negative for s in scores)
    n = len(scores) or 1
    return {
        "cases": len(scores),
        "precision": tp / (tp + fp) if tp + fp else 1.0,
        "recall": tp / (tp + fn) if tp + fn else 1.0,
        "exact_rate": sum(s.exact for s in scores) / n,
        "not_understood_accuracy": sum(s.not_understood_ok for s in scores) / n,
    }


@dataclass
class NarrativeScore:
    case_id: str
    verified: bool
    cited: list[str]
    missing_citations: list[str]
    required: int = 0
    rejection: str | None = None


def score_narrative(case: NarrativeCase, cited: list[str] | None, rejection: str | None = None) -> NarrativeScore:
    if cited is None:
        return NarrativeScore(case.case_id, False, [], list(case.must_cite), len(case.must_cite), rejection)
    return NarrativeScore(case.case_id, True, cited, [k for k in case.must_cite if k not in cited], len(case.must_cite))


def summarize_narrative(scores: list[NarrativeScore]) -> dict[str, float]:
    n = len(scores) or 1
    # Solo i KPI certi che il caso chiede di citare; un testo rifiutato non cita niente.
    wanted = sum(s.required for s in scores)
    found = sum(s.required - len(s.missing_citations) for s in scores)
    return {
        "cases": len(scores),
        "verified_rate": sum(s.verified for s in scores) / n,
        "citation_recall": found / wanted if wanted else 1.0,
    }
