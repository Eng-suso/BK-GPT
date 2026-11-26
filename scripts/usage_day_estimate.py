"""Quanto costa una giornata tipica di un consulente, stimato dal codice.

Non e' una misura: e' una stima senza spendere. Le dimensioni dei pezzi fissi
(prompt di sistema, schemi di output, definizioni dei tool, memoria procedurale)
si leggono dal codice vero; le dimensioni dei pezzi variabili (lunghezza di
un'intervista, contesto di scope, turni al giorno) sono ipotesi scritte qui
sotto, in `DAY`, e si cambiano li'. La misura vera resta
`scripts/llm_spend.py --giorni 1` con il listino configurato.

I token si stimano come caratteri / 4: l'encoding vero non e' scaricabile in
questo ambiente, e i due modelli hanno tokenizer diversi. Va letto come
±20%.

    uv run python scripts/usage_day_estimate.py
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

CHARS_PER_TOKEN = 4

# Listini ufficiali, USD per milione di token (verificati il 2026-11-26):
# - GPT-6 Luna: developers.openai.com/api/docs/models/gpt-6-luna
# - Claude Haiku 5.5: platform.claude.com/docs/en/about-claude/pricing
# - text-embedding-3-small: developers.openai.com/api/docs/models/text-embedding-3-small
PRICES = {
    "gpt-6-luna": {"input": 0.10, "cached": 0.01, "cache_write": 0.125, "output": 0.50, "long_context_tokens": 272_000},
    "claude-haiku-5-5": {"input": 0.10, "cached": 0.01, "cache_write": 0.125, "output": 0.50, "long_context_tokens": 100_000},
}
EMBEDDING_PRICE = 0.02

# La giornata tipica di un consulente in prova. Ogni numero e' un'ipotesi.
DAY = {
    "interviews": 2,  # trascrizioni caricate nel giorno
    "interview_chars": 40_000,  # ~45 minuti di intervista
    "plan_syntheses": 2,  # ricostruzioni del piano (leggono tutte le fonti del processo)
    "bpmn_drafts": 2,  # «Genera BPMN»
    "conformance_sources": 2,  # fonti confrontate col disegno, una chiamata ciascuna
    "chat_turns": 40,
    "steps_per_turn": 2.5,  # passi del ciclo agente per turno
    "specialist_mix": {"discovery": 0.4, "evidence": 0.3, "modeling": 0.3},
    "scope_context_tokens": 12_000,  # piano + modello + XML nel prompt (tetto: 48.000)
    "history_tokens": 2_500,  # messaggi recenti della conversazione
    "step_output_tokens": 350,
    "summary_every_turns": 8,
    "rerank_per_turn": 0.5,
    "entity_resolutions": 20,
    "what_ifs": 3,
    "narratives": 2,
    "claim_matchings": 2,
    "memory_facts": 10,
    # Quota di input servita dalla cache nei passi di chat dopo il primo di una
    # serie (prefisso statico: memoria procedurale + tool). 0 = scenario peggiore.
    "chat_cache_share": 0.6,
}

# Token di ragionamento in rapporto all'uscita, per livello chiesto dal profilo.
REASONING = {"none": 0.0, "low": 0.3, "medium": 1.0}


def tokens(text: str | int) -> int:
    return (text if isinstance(text, int) else len(text)) // CHARS_PER_TOKEN


def schema_tokens(model) -> int:
    return tokens(json.dumps(model.model_json_schema(), ensure_ascii=False))


def tool_tokens(tools) -> int:
    from langchain_core.utils.function_calling import convert_to_openai_tool

    return tokens(json.dumps([convert_to_openai_tool(t) for t in tools], ensure_ascii=False))


@dataclass
class Line:
    """Una voce della giornata: quante chiamate e quanti token per chiamata."""

    name: str
    calls: float
    input_tokens: int
    output_tokens: int
    effort: str = "none"
    cached_share: float = 0.0
    notes: str = ""

    def per_day(self) -> tuple[float, float, float]:
        total_in = self.calls * self.input_tokens
        cached = total_in * self.cached_share
        out = self.calls * self.output_tokens * (1 + REASONING[self.effort])
        return total_in - cached, cached, out


@dataclass
class Day:
    lines: list[Line] = field(default_factory=list)
    embedding_tokens: int = 0


def measure() -> dict[str, int]:
    """I pezzi fissi, letti dal codice."""
    from backend.agent import PROCEDURAL_MEMORY_PATH
    from backend.agents.conformance_audit import AUDITOR_PROMPT, SourceAuditVerdict
    from backend.graphs.process.subgraphs.discovery.tools import discovery_tools
    from backend.graphs.process.subgraphs.evidence.tools import evidence_tools
    from backend.graphs.process.subgraphs.modeling.tools import modeling_tools
    from backend.memory.consultant_context_classifier import SISTEMA_CLASSIFICAZIONE
    from backend.memory.knowledge_graph.entity_resolution import _SISTEMA as ER_SYSTEM
    from backend.process_understanding import (
        _PROCESS_UNDERSTANDING_PROMPT,
        _PROCESS_UNDERSTANDING_QUALITY_PROMPT,
        ProcessUnderstanding,
        ProcessUnderstandingQualityReport,
    )
    from backend.simulation.narrative import SYSTEM as NARRATIVE_SYSTEM
    from backend.simulation.whatif import SYSTEM as WHATIF_SYSTEM
    from backend.workspace_services.evidence.claims import SYSTEM as CLAIMS_SYSTEM
    from backend.workspace_services.evidence.claims import ClaimExtraction
    from backend.workspace_services.evidence.reconcile import SYSTEM as RECONCILE_SYSTEM
    from backend.workspace_services.evidence.reconcile import Reconciliation

    return {
        "procedural": tokens(PROCEDURAL_MEMORY_PATH.read_text(encoding="utf-8")),
        "tools_discovery": tool_tokens(discovery_tools),
        "tools_evidence": tool_tokens(evidence_tools),
        "tools_modeling": tool_tokens(modeling_tools),
        "routing_system": tokens(SISTEMA_CLASSIFICAZIONE),
        "plan_prompt": tokens(_PROCESS_UNDERSTANDING_PROMPT) + schema_tokens(ProcessUnderstanding),
        "quality_prompt": tokens(_PROCESS_UNDERSTANDING_QUALITY_PROMPT) + schema_tokens(ProcessUnderstandingQualityReport),
        "audit_prompt": tokens(AUDITOR_PROMPT) + schema_tokens(SourceAuditVerdict),
        "claims_prompt": tokens(CLAIMS_SYSTEM) + schema_tokens(ClaimExtraction),
        "reconcile_prompt": tokens(RECONCILE_SYSTEM) + schema_tokens(Reconciliation),
        "er_prompt": tokens(ER_SYSTEM),
        "whatif_prompt": tokens(WHATIF_SYSTEM),
        "narrative_prompt": tokens(NARRATIVE_SYSTEM),
    }


def build_day(m: dict[str, int], d: dict) -> Day:
    interview = tokens(d["interview_chars"])
    sources = interview * d["interviews"]
    day = Day()
    add = day.lines.append

    # Fonti: estrazione delle affermazioni e confronto con gli altri file.
    add(Line("source_claims", d["interviews"], m["claims_prompt"] + interview, 3_000, "medium"))
    add(Line("source_reconcile", d["interviews"], m["reconcile_prompt"] + 4_000, 1_500, "medium"))
    # Piano: estrazione da tutte le fonti del processo, poi il controllo di qualita'.
    add(Line("plan_extraction", d["plan_syntheses"], m["plan_prompt"] + sources, 6_000, "medium"))
    add(Line("plan_quality", d["plan_syntheses"], m["quality_prompt"] + 6_000, 1_200, "low"))
    # Disegno: la modellazione gira dentro un turno di chat (sotto), l'audit per fonte.
    add(Line("conformance_audit", d["conformance_sources"] * d["bpmn_drafts"], m["audit_prompt"] + 6_000 + interview // 2, 2_000, "medium"))

    # Chat: ogni passo rimanda memoria procedurale, tool dello specialista, contesto e storia.
    turns, steps = d["chat_turns"], d["steps_per_turn"]
    variable = d["scope_context_tokens"] + d["history_tokens"]
    for specialist, share in d["specialist_mix"].items():
        static = m["procedural"] + m[f"tools_{specialist}"]
        calls = turns * steps * share
        # Il primo passo di ogni turno paga tutto; gli altri trovano in cache il prefisso statico.
        first_share = 1 / steps
        cached = (1 - first_share) * d["chat_cache_share"] * static / (static + variable)
        add(Line(f"chat_turn ({specialist})", calls, static + variable, d["step_output_tokens"], "none", cached))
    add(Line("context_routing", turns, m["routing_system"] + 800, 80))
    add(Line("thread_summary", turns / d["summary_every_turns"], 4_000, 600))
    add(Line("retrieval_rerank", turns * d["rerank_per_turn"], 2_000, 100))

    # Grafo e memoria.
    add(Line("entity_resolution", d["entity_resolutions"], m["er_prompt"] + 250, 40))
    day.embedding_tokens = sources + d["entity_resolutions"] * 3 * 8 + d["memory_facts"] * 60 + turns * 30

    # Simulazione.
    add(Line("simulation_what_if", d["what_ifs"], m["whatif_prompt"] + 1_500, 400))
    add(Line("simulation_narrative", d["narratives"], m["narrative_prompt"] + 1_200, 400))
    add(Line("claim_matching", d["claim_matchings"], 2_500, 300))
    return day


def cost(day: Day, model: str) -> tuple[float, list[tuple[str, float, int]]]:
    p = PRICES[model]
    rows = []
    total = 0.0
    for line in day.lines:
        fresh, cached, out = line.per_day()
        c = (fresh * p["input"] + cached * p["cached"] + out * p["output"]) / 1e6
        rows.append((line.name, c, line.input_tokens))
        total += c
    total += day.embedding_tokens * EMBEDDING_PRICE / 1e6
    return total, rows


def main() -> None:
    m = measure()
    print("Pezzi fissi letti dal codice (token stimati):")
    for key, value in m.items():
        print(f"  {key:20s} {value:>8,}")

    day = build_day(m, DAY)
    worst = build_day(m, {**DAY, "chat_cache_share": 0.0})
    heavy = build_day(m, {**DAY, "chat_turns": 100, "interviews": 4, "plan_syntheses": 4, "bpmn_drafts": 4})

    for model in PRICES:
        total, rows = cost(day, model)
        print(f"\n{model}: giornata tipica ${total:.4f}")
        for name, c, per_call in sorted(rows, key=lambda r: -r[1]):
            print(f"  {name:28s} ${c:.4f}   ({per_call:,} token in per chiamata)")
        print(f"  {'embedding':28s} ${day.embedding_tokens * EMBEDDING_PRICE / 1e6:.4f}")
        print(f"  senza cache:      ${cost(worst, model)[0]:.4f}")
        print(f"  giornata pesante: ${cost(heavy, model)[0]:.4f}")
        biggest = max(line.input_tokens for line in heavy.lines)
        limit = PRICES[model]["long_context_tokens"]
        flag = "OLTRE la soglia: prezzo maggiorato" if biggest > limit else "sotto la soglia"
        print(f"  prompt piu' lungo (giornata pesante): {biggest:,} token, soglia {limit:,} -> {flag}")


if __name__ == "__main__":
    main()
