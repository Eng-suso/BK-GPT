"""Quanto costa un consulente al giorno, stimato dal codice: tipico e uso intenso.

Non e' una misura: e' una stima senza spendere. Le dimensioni dei pezzi fissi
(prompt di sistema, schemi di output, definizioni dei tool di ogni specialista,
memoria procedurale) si leggono dal codice vero; i pezzi variabili (quante
interviste, quanti turni, quanto contesto) sono ipotesi scritte in `SCENARIOS`, e
si cambiano li'. La misura vera resta `scripts/llm_spend.py --giorni 1` con il
listino configurato.

Copre **ogni** compito che spende: tutti i valori di `LlmTask` (lo script si
ferma se ne manca uno) piu' la trascrizione dal vivo, che non passa dal gateway.

I token si stimano come caratteri / 4: l'encoding vero non e' scaricabile in
questo ambiente e i due modelli hanno tokenizer diversi. Va letto come ±20%.

    uv run python scripts/usage_day_estimate.py
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

CHARS_PER_TOKEN = 4

# Listini ufficiali, USD (verificati il 2026-11-26):
# - GPT-6 Luna: developers.openai.com/api/docs/models/gpt-6-luna
# - Claude Haiku 5.5: platform.claude.com/docs/en/about-claude/pricing
# - text-embedding-3-small: developers.openai.com/api/docs/models/text-embedding-3-small
# - gpt-realtime-whisper: $0.017 al minuto (developers.openai.com/api/docs/models/gpt-realtime-whisper)
# - gpt-4o-transcribe-diarize: tariffa a token di gpt-4o-transcribe, che OpenAI
#   stima a $0.006 al minuto; il modello e' deprecato e non ha un prezzo al minuto suo.
PRICES = {
    "gpt-6-luna": {"input": 0.10, "cached": 0.01, "output": 0.50, "long_context_tokens": 272_000},
    "claude-haiku-5-5": {"input": 0.10, "cached": 0.01, "output": 0.50, "long_context_tokens": 100_000},
}
EMBEDDING_PER_M = 0.02
TRANSCRIPTION_PER_MIN = 0.006
LIVE_TRANSCRIPTION_PER_MIN = 0.017

# Token di ragionamento in rapporto all'uscita, per livello chiesto dal profilo.
REASONING = {"none": 0.0, "low": 0.3, "medium": 1.0}

# Gli specialisti della chat e i tool che ciascuno manda a ogni passo.
CHAT_SPECIALISTS = (
    "home", "clients", "setup",  # consulenza
    "discovery", "evidence", "modeling",  # processo
    "canvas_macro", "canvas_patch", "canvas_construction",  # canvas
    "review",  # revisione di un'attivita'
)

SCENARIOS: dict[str, dict] = {
    "tipica": {
        "interviews": 2, "interview_chars": 40_000,
        "documents": 0, "document_chars": 30_000,
        "audio_minutes_uploaded": 0, "audio_minutes_live": 0,
        "processes": 1, "plan_syntheses": 2, "plan_unifications": 0,
        "bpmn_drafts": 2, "conformance_repairs": 0,
        "chat_turns": 40, "steps_per_turn": 2.5,
        "chat_mix": {"discovery": 0.4, "evidence": 0.3, "modeling": 0.3},
        "scope_context_tokens": 12_000, "history_tokens": 2_500, "step_output_tokens": 350,
        "summary_every_turns": 8, "rerank_per_turn": 0.5,
        "entity_resolutions": 20, "memory_facts": 10, "memory_infer": False,
        "playbook_extractions": 0, "playbook_generalizations": 0,
        "what_ifs": 3, "narratives": 2, "claim_matchings": 2,
        "chat_cache_share": 0.6,
    },
    "intensa": {
        # Tre processi nello stesso giorno, tutte le fonti possibili, chat quasi
        # continua su ogni specialista, trascrizione di tre ore di interviste.
        "interviews": 4, "interview_chars": 40_000,
        "documents": 6, "document_chars": 30_000,
        "audio_minutes_uploaded": 60, "audio_minutes_live": 120,
        "processes": 3, "plan_syntheses": 6, "plan_unifications": 3,
        "bpmn_drafts": 6, "conformance_repairs": 2,
        "chat_turns": 150, "steps_per_turn": 3.0,
        "chat_mix": {
            "home": 0.05, "clients": 0.05, "setup": 0.05,
            "discovery": 0.15, "evidence": 0.2, "modeling": 0.2,
            "canvas_macro": 0.08, "canvas_patch": 0.08, "canvas_construction": 0.04,
            "review": 0.1,
        },
        "scope_context_tokens": 24_000, "history_tokens": 4_000, "step_output_tokens": 450,
        "summary_every_turns": 6, "rerank_per_turn": 1.0,
        "entity_resolutions": 80, "memory_facts": 30, "memory_infer": True,
        "playbook_extractions": 3, "playbook_generalizations": 1,
        "what_ifs": 15, "narratives": 6, "claim_matchings": 6,
        "chat_cache_share": 0.6,
    },
}


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

    task: str
    calls: float
    input_tokens: int
    output_tokens: int
    effort: str = "none"
    cached_share: float = 0.0
    label: str = ""

    def per_day(self) -> tuple[float, float, float]:
        total_in = self.calls * self.input_tokens
        cached = total_in * self.cached_share
        out = self.calls * self.output_tokens * (1 + REASONING[self.effort])
        return total_in - cached, cached, out


def measure() -> dict[str, int]:
    """I pezzi fissi, letti dal codice."""
    from backend.agent import PROCEDURAL_MEMORY_PATH
    from backend.agents.conformance_audit import AUDITOR_PROMPT, SourceAuditVerdict
    from backend.agents.plan_consolidation import PlanUnificationVerdict
    from backend.graphs.canvas_edit.tools import canvas_macro_tools, construction_tools, patch_edit_tools
    from backend.graphs.consulting.subgraphs.clients.tools import clients_tools
    from backend.graphs.consulting.subgraphs.home.tools import home_tools
    from backend.graphs.consulting.subgraphs.setup.tools import setup_tools
    from backend.graphs.process.subgraphs.discovery.tools import discovery_tools
    from backend.graphs.process.subgraphs.evidence.tools import evidence_tools
    from backend.graphs.process.subgraphs.modeling.tools import modeling_tools
    from backend.graphs.task_review import REVIEW_TOOLS
    from backend.memory.consultant_context_classifier import SISTEMA_CLASSIFICAZIONE
    from backend.memory.knowledge_graph.entity_resolution import _SISTEMA as ER_SYSTEM
    from backend.memory.procedural.extraction import ExtractedPlaybook, GeneralizedPlaybook
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

    tools = {
        "home": home_tools, "clients": clients_tools, "setup": setup_tools,
        "discovery": discovery_tools, "evidence": evidence_tools, "modeling": modeling_tools,
        "canvas_macro": canvas_macro_tools, "canvas_patch": patch_edit_tools,
        "canvas_construction": construction_tools, "review": REVIEW_TOOLS,
    }
    return {
        "procedural": tokens(PROCEDURAL_MEMORY_PATH.read_text(encoding="utf-8")),
        **{f"tools_{name}": tool_tokens(group) for name, group in tools.items()},
        "routing_system": tokens(SISTEMA_CLASSIFICAZIONE),
        "plan_prompt": tokens(_PROCESS_UNDERSTANDING_PROMPT) + schema_tokens(ProcessUnderstanding),
        "quality_prompt": tokens(_PROCESS_UNDERSTANDING_QUALITY_PROMPT) + schema_tokens(ProcessUnderstandingQualityReport),
        "unification_prompt": schema_tokens(PlanUnificationVerdict) + 600,
        "audit_prompt": tokens(AUDITOR_PROMPT) + schema_tokens(SourceAuditVerdict),
        "claims_prompt": tokens(CLAIMS_SYSTEM) + schema_tokens(ClaimExtraction),
        "reconcile_prompt": tokens(RECONCILE_SYSTEM) + schema_tokens(Reconciliation),
        "er_prompt": tokens(ER_SYSTEM),
        "playbook_prompt": schema_tokens(ExtractedPlaybook) + 600,
        "generalization_prompt": schema_tokens(GeneralizedPlaybook) + 600,
        "whatif_prompt": tokens(WHATIF_SYSTEM),
        "narrative_prompt": tokens(NARRATIVE_SYSTEM),
    }


def build_day(m: dict[str, int], d: dict) -> tuple[list[Line], dict[str, float]]:
    """Le voci della giornata, e le spese non a token (embedding, audio)."""
    interview, document = tokens(d["interview_chars"]), tokens(d["document_chars"])
    sources = d["interviews"] + d["documents"]
    source_tokens = d["interviews"] * interview + d["documents"] * document
    per_process = source_tokens / max(1, d["processes"])
    sources_per_process = sources / max(1, d["processes"])
    mean_source = source_tokens / max(1, sources)
    lines: list[Line] = []
    add = lines.append

    # Fonti: affermazioni e confronto con gli altri file, una volta per fonte.
    add(Line("source_claims", sources, m["claims_prompt"] + int(mean_source), 3_000, "medium"))
    add(Line("source_reconcile", sources, m["reconcile_prompt"] + 4_000, 1_500, "medium"))
    # Piano: estrazione da tutte le fonti del processo, qualita', unificazione fra fonti.
    add(Line("plan_extraction", d["plan_syntheses"], m["plan_prompt"] + int(per_process), 6_000, "medium"))
    add(Line("plan_quality", d["plan_syntheses"], m["quality_prompt"] + 6_000, 1_200, "low"))
    add(Line("plan_unification", d["plan_unifications"], m["unification_prompt"] + 3 * 6_000, 2_000, "medium"))
    # Disegno: l'audit gira per fonte; la riparazione rifa' piano e audit.
    audits = (d["bpmn_drafts"] + d["conformance_repairs"]) * sources_per_process
    add(Line("conformance_audit", audits, m["audit_prompt"] + 6_000 + int(mean_source / 2), 2_000, "medium"))
    add(Line("plan_extraction", d["conformance_repairs"], m["plan_prompt"] + int(per_process), 6_000, "medium", label="plan_extraction (riparazione)"))

    # Chat: ogni passo rimanda memoria procedurale, tool dello specialista, contesto e storia.
    turns, steps = d["chat_turns"], d["steps_per_turn"]
    variable = d["scope_context_tokens"] + d["history_tokens"]
    for specialist, share in d["chat_mix"].items():
        static = m["procedural"] + m[f"tools_{specialist}"]
        # Il primo passo di ogni turno paga tutto; gli altri trovano in cache il prefisso statico.
        cached = (1 - 1 / steps) * d["chat_cache_share"] * static / (static + variable)
        add(Line("chat_turn", turns * steps * share, static + variable, d["step_output_tokens"], "none", cached, f"chat_turn ({specialist})"))
    add(Line("context_routing", turns, m["routing_system"] + 800, 80))
    add(Line("thread_summary", turns / d["summary_every_turns"], 4_000, 600))
    add(Line("retrieval_rerank", turns * d["rerank_per_turn"], 2_000, 100))

    # Grafo e memoria.
    add(Line("entity_resolution", d["entity_resolutions"], m["er_prompt"] + 250, 40))
    add(Line("playbook_extraction", d["playbook_extractions"], m["playbook_prompt"] + 6_000, 800, "low"))
    add(Line("playbook_generalization", d["playbook_generalizations"], m["generalization_prompt"] + 3_000, 600, "low"))
    # Mem0 con l'estrazione dei fatti accesa: due chiamate per fatto (estrai, decidi).
    memory_calls = d["memory_facts"] * 2 if d["memory_infer"] else 0
    add(Line("memory_extraction", memory_calls, 1_500, 200))

    # Simulazione.
    add(Line("simulation_what_if", d["what_ifs"], m["whatif_prompt"] + 1_500, 400))
    add(Line("simulation_narrative", d["narratives"], m["narrative_prompt"] + 1_200, 400))
    add(Line("claim_matching", d["claim_matchings"], 2_500, 300))

    embedding_tokens = (
        source_tokens  # chunk del grafo, una volta per fonte
        + d["entity_resolutions"] * 3 * 8  # nomi delle entita'
        + turns * 30  # ricerche nel grafo e nella memoria
    )
    memory_embedding_tokens = d["memory_facts"] * 60 + turns * 30
    extras = {
        "embedding": embedding_tokens * EMBEDDING_PER_M / 1e6,
        "memory_embedding": memory_embedding_tokens * EMBEDDING_PER_M / 1e6,
        "transcription": d["audio_minutes_uploaded"] * TRANSCRIPTION_PER_MIN,
        "live_transcription": d["audio_minutes_live"] * LIVE_TRANSCRIPTION_PER_MIN,
    }
    return lines, extras


def check_coverage(lines: list[Line], extras: dict[str, float]) -> None:
    """Ogni compito che spende deve stare nella stima: un compito nuovo la rompe."""
    from backend.llm import LlmTask

    covered = {line.task for line in lines} | set(extras)
    # Il giudice degli eval non gira in produzione: non e' spesa di un consulente.
    missing = {task.value for task in LlmTask} - covered - {LlmTask.EVAL_JUDGE.value}
    if missing:
        raise SystemExit(f"compiti senza stima: {sorted(missing)}")


def cost(lines: list[Line], extras: dict[str, float], model: str) -> tuple[float, dict[str, float]]:
    p = PRICES[model]
    by_label: dict[str, float] = {}
    for line in lines:
        fresh, cached, out = line.per_day()
        c = (fresh * p["input"] + cached * p["cached"] + out * p["output"]) / 1e6
        key = line.label or line.task
        by_label[key] = by_label.get(key, 0.0) + c
    by_label.update(extras)
    return sum(by_label.values()), by_label


def main() -> None:
    m = measure()
    print("Pezzi fissi letti dal codice (token stimati):")
    for key, value in m.items():
        print(f"  {key:26s} {value:>8,}")

    for name, scenario in SCENARIOS.items():
        lines, extras = build_day(m, scenario)
        check_coverage(lines, extras)
        worst_lines, worst_extras = build_day(m, {**scenario, "chat_cache_share": 0.0})
        for model in PRICES:
            total, rows = cost(lines, extras, model)
            print(f"\n[{name}] {model}: ${total:.3f} al giorno (senza cache ${cost(worst_lines, worst_extras, model)[0]:.3f})")
            for label, c in sorted(rows.items(), key=lambda r: -r[1]):
                if c:
                    print(f"  {label:34s} ${c:.4f}  {c / total:5.1%}")
            biggest = max(line.input_tokens for line in lines if line.calls)
            limit = PRICES[model]["long_context_tokens"]
            note = "OLTRE la soglia: prezzo maggiorato" if biggest > limit else "sotto la soglia"
            print(f"  prompt piu' lungo: {biggest:,} token (soglia {limit:,}: {note})")


if __name__ == "__main__":
    main()
