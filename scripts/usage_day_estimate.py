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
#
# La cache dei due fornitori non funziona allo stesso modo, e per la chat e' la
# differenza che conta:
# - OpenAI mette in cache da solo ogni prefisso gia' visto, senza sovrapprezzo
#   di scrittura (`cache_write` 1.0);
# - Anthropic mette in cache solo dove la richiesta lo chiede (`cache_control`),
#   e la scrittura costa 1,25 volte l'ingresso con la durata di 5 minuti.
#   Senza segnalibri non c'e' cache: `marked=False` misura quel caso.
PRICES = {
    "gpt-6-luna": {
        "input": 0.10, "cached": 0.01, "output": 0.50, "long_context_tokens": 272_000,
        "cache_write": 1.0,
    },
    "claude-haiku-5-5": {
        "input": 0.10, "cached": 0.01, "output": 0.50, "long_context_tokens": 100_000,
        "cache_write": 1.25,
    },
}
EMBEDDING_PER_M = 0.02
TRANSCRIPTION_PER_MIN = 0.006
LIVE_TRANSCRIPTION_PER_MIN = 0.017

# Token di ragionamento in rapporto all'uscita, per livello chiesto dal profilo.
REASONING = {"none": 0.0, "low": 0.3, "medium": 1.0}

# Gli specialisti della chat, con i tool e il contratto che ciascuno manda a ogni passo.
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
        "tool_result_tokens": 1_200, "tool_call_tokens": 150,
        # Quanto spesso il primo passo trova in cache la parte fissa (lo stesso
        # specialista ha lavorato da poco, per un consulente qualsiasi), e quanto
        # spesso anche lo scope (stesso processo del turno prima). La seconda e'
        # una probabilita' congiunta: lo scope viene dopo, non puo' superarla.
        "head_cache_hit": 0.6, "scope_cache_hit": 0.3,
        # Quota dei passi con la finestra della storia gia' piena (thread lunghi).
        "history_window_full": 0.6,
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
        "tool_result_tokens": 1_500, "tool_call_tokens": 200,
        "head_cache_hit": 0.9, "scope_cache_hit": 0.5,
        "history_window_full": 0.8,
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
    # La parte nuova di questa chiamata viene scritta in cache: dove la scrittura
    # ha un sovrapprezzo (Anthropic), lo paga.
    cache_written: bool = False

    def per_day(self) -> tuple[float, float, float]:
        total_in = self.calls * self.input_tokens
        cached = total_in * self.cached_share
        out = self.calls * self.output_tokens * (1 + REASONING[self.effort])
        return total_in - cached, cached, out


def measure() -> dict[str, int]:
    """I pezzi fissi, letti dal codice."""
    from backend.agent import PROCEDURAL_MEMORY_PATH, RECENT_MESSAGE_LIMIT
    from backend.agents.conformance_audit import AUDITOR_PROMPT, SourceAuditVerdict
    from backend.agents.plan_consolidation import PlanUnificationVerdict
    from backend.graphs.canvas_edit.graph import CANVAS_SUBGRAPH_CONTRACT
    from backend.graphs.canvas_edit.subgraphs.construction.graph import CONSTRUCTION_SUBGRAPH_CONTRACT
    from backend.graphs.canvas_edit.subgraphs.patch_edit.graph import PATCH_EDIT_SUBGRAPH_CONTRACT
    from backend.graphs.canvas_edit.tools import canvas_macro_tools, construction_tools, patch_edit_tools
    from backend.graphs.consulting.subgraphs.clients.graph import CLIENTS_SUBGRAPH_CONTRACT
    from backend.graphs.consulting.subgraphs.home.graph import HOME_SUBGRAPH_CONTRACT
    from backend.graphs.consulting.subgraphs.setup.graph import SETUP_SUBGRAPH_CONTRACT
    from backend.graphs.process.subgraphs.discovery.graph import DISCOVERY_SUBGRAPH_CONTRACT
    from backend.graphs.process.subgraphs.evidence.graph import EVIDENCE_SUBGRAPH_CONTRACT
    from backend.graphs.process.subgraphs.modeling.graph import MODELING_SUBGRAPH_CONTRACT
    from backend.graphs.consulting.subgraphs.clients.tools import clients_tools
    from backend.graphs.consulting.subgraphs.home.tools import home_tools
    from backend.graphs.consulting.subgraphs.setup.tools import setup_tools
    from backend.graphs.process.subgraphs.discovery.tools import discovery_tools
    from backend.graphs.process.subgraphs.evidence.tools import evidence_tools
    from backend.graphs.process.subgraphs.modeling.tools import modeling_tools
    from backend.graphs.task_review import REVIEW_CONTRACT, REVIEW_TOOLS
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

    # Ogni specialista: i tool che manda e il contratto che riceve, come li passa
    # il suo grafo a `build_tool_chat_subgraph`.
    specialists = {
        "home": (home_tools, HOME_SUBGRAPH_CONTRACT),
        "clients": (clients_tools, CLIENTS_SUBGRAPH_CONTRACT),
        "setup": (setup_tools, SETUP_SUBGRAPH_CONTRACT),
        "discovery": (discovery_tools, DISCOVERY_SUBGRAPH_CONTRACT),
        "evidence": (evidence_tools, EVIDENCE_SUBGRAPH_CONTRACT),
        "modeling": (modeling_tools, MODELING_SUBGRAPH_CONTRACT),
        "canvas_macro": (canvas_macro_tools, CANVAS_SUBGRAPH_CONTRACT),
        "canvas_patch": (patch_edit_tools, PATCH_EDIT_SUBGRAPH_CONTRACT),
        "canvas_construction": (construction_tools, CONSTRUCTION_SUBGRAPH_CONTRACT),
        "review": (REVIEW_TOOLS, REVIEW_CONTRACT),
    }
    if set(specialists) != set(CHAT_SPECIALISTS):
        raise SystemExit("CHAT_SPECIALISTS e gli specialisti misurati non coincidono")
    # I due tool che portano lo schema intero del piano: la leva "tool per passo".
    heavy = [t for t in modeling_tools if t.name in {"amend_process_plan", "prepare_process_understanding_review"}]
    return {
        "procedural": tokens(PROCEDURAL_MEMORY_PATH.read_text(encoding="utf-8")),
        "history_window_messages": RECENT_MESSAGE_LIMIT,
        **{f"tools_{name}": tool_tokens(tools) for name, (tools, _) in specialists.items()},
        **{f"contract_{name}": tokens(contract) for name, (_, contract) in specialists.items()},
        "tools_modeling_heavy": tool_tokens(heavy),
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


def build_day(
    m: dict[str, int], d: dict, *, contract_in_head: bool = False, stable_window: bool = False
) -> tuple[list[Line], dict[str, float]]:
    """Le voci della giornata, e le spese non a token (embedding, audio).

    I due flag misurano leve che il codice non ha ancora, perche' cambiano cio'
    che il modello legge e vanno prima validate con gli eval della chat:
    `contract_in_head` mette il contratto dello specialista nella parte fissa in
    testa; `stable_window` tiene ferma per tutto il turno la finestra della storia.
    """
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

    # Chat: il prompt di un passo, nell'ordine in cui `build_tool_chat_subgraph`
    # lo costruisce. Il fornitore mette in cache un prefisso, quindi conta
    # l'ordine, non solo la dimensione:
    #
    #   [tool + memoria procedurale] [scope] [storia: ultimi N messaggi] [contratto]
    #    fisso, uguale per tutti      per processo  scorre a ogni passo    in coda
    #
    # - primo passo del turno: la parte fissa e' in cache se lo stesso specialista
    #   ha girato da poco, per un consulente qualsiasi; lo scope se e' anche lo
    #   stesso processo del turno prima (quindi `scope_cache_hit` <= `head_cache_hit`);
    # - passi successivi: la storia e' una finestra degli ultimi N messaggi
    #   (`RECENT_MESSAGE_LIMIT`, letto dal codice in `measure`). A finestra piena ogni passo ne fa uscire i piu'
    #   vecchi, tutto cio' che segue lo scope cambia e la cache si ferma li'.
    #   Solo a finestra non ancora piena il passo prima e' un prefisso intero;
    # - il contratto sta in coda: non entra mai nel prefisso e si paga intero.
    turns, steps = d["chat_turns"], d["steps_per_turn"]
    scope, history = d["scope_context_tokens"], d["history_tokens"]
    # Un passo aggiunge la chiamata del tool e il suo risultato.
    step_added = d["tool_result_tokens"] + d["tool_call_tokens"]
    head_hit, scope_hit = d["head_cache_hit"], d["scope_cache_hit"]
    if scope_hit > head_hit:
        raise SystemExit("scope_cache_hit non puo' superare head_cache_hit: lo scope viene dopo")
    window_full = 0.0 if stable_window else d["history_window_full"]
    for specialist, share in d["chat_mix"].items():
        head = m["procedural"] + m[f"tools_{specialist}"]
        contract = m[f"contract_{specialist}"]
        if contract_in_head:
            head, contract = head + contract, 0
        first_in = head + scope + history + contract
        first_cached = head_hit * head + scope_hit * scope
        # Il passo k (2..S) porta k-1 chiamate fatte: in media S/2.
        later_in = head + scope + history + step_added * steps / 2 + contract
        # A finestra non piena e' in cache tutto il passo prima: il prompt meno
        # l'ultima chiamata e il contratto in coda.
        extends_previous = head + scope + history + step_added * (steps / 2 - 1)
        later_cached = window_full * (head + scope) + (1 - window_full) * extends_previous
        calls = turns * share
        for n, prompt, cached in ((calls, first_in, first_cached), (calls * (steps - 1), later_in, later_cached)):
            if n > 0:
                add(Line("chat_turn", n, int(prompt), d["step_output_tokens"], "none",
                         cached / prompt, f"chat_turn ({specialist})", cache_written=True))
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


def cost(
    lines: list[Line], extras: dict[str, float], model: str, *, cache: bool = True
) -> tuple[float, dict[str, float]]:
    """Il costo della giornata. `cache=False` e' il caso senza cache: per Haiku,
    un client che non mette i segnalibri `cache_control`."""
    p = PRICES[model]
    by_label: dict[str, float] = {}
    for line in lines:
        fresh, cached, out = line.per_day()
        if not cache:
            fresh, cached = fresh + cached, 0.0
        write = p["cache_write"] if cache and line.cache_written else 1.0
        c = (fresh * p["input"] * write + cached * p["cached"] + out * p["output"]) / 1e6
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
        # Le leve sulla chat: la stessa giornata con una cosa cambiata.
        levers = {
            "contratto in testa (da validare con gli eval)": build_day(m, scenario, contract_in_head=True),
            "finestra della storia ferma per il turno (da validare)": build_day(m, scenario, stable_window=True),
            "tool del piano tolti dalla modellazione (tetto massimo)": build_day(
                {**m, "tools_modeling": m["tools_modeling"] - m["tools_modeling_heavy"]}, scenario
            ),
        }
        for model in PRICES:
            total, rows = cost(lines, extras, model)
            uncached = cost(lines, extras, model, cache=False)[0]
            how = "con i segnalibri cache_control" if PRICES[model]["cache_write"] > 1 else "cache automatica"
            print(f"\n[{name}] {model}: ${total:.3f} al giorno ({how}; senza cache ${uncached:.3f})")
            for label, c in sorted(rows.items(), key=lambda r: -r[1]):
                if c:
                    print(f"  {label:34s} ${c:.4f}  {c / total:5.1%}")
            biggest = max(line.input_tokens for line in lines if line.calls)
            limit = PRICES[model]["long_context_tokens"]
            note = "OLTRE la soglia: prezzo maggiorato" if biggest > limit else "sotto la soglia"
            print(f"  prompt piu' lungo: {biggest:,} token (soglia {limit:,}: {note})")

            for lever, variant in levers.items():
                print(f"  leva: {lever}  -${total - cost(*variant, model)[0]:.3f}")


if __name__ == "__main__":
    main()
