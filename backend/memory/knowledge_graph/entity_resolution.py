"""Entity resolution (P2): "questa entita' e' gia' nel grafo?".

Prima di inserire una `kg_entity`, il writer (`canonical.write_entity`) chiede
qui se il nome che sta per scrivere e' la stessa cosa del mondo reale di
un'entita' gia' nota per quel cliente. Se si', il writer aggiorna l'entita'
esistente (alias + provenance + confidence) invece di crearne una seconda.

Tre livelli, dal piu' certo al piu' incerto:

  0. **esatto** — `canonical_name` o un `alias` coincide (whitespace normalizzato,
     case-insensitive). Deciso senza LLM.
  1. **candidati** — nomi lessicalmente simili (`pg_trgm`) o semanticamente
     vicini (coseno sull'embedding del nome). Sono solo candidati: la
     calibrazione (`docs`/commit P2.2) mostra che coseno e trigram sui nomi
     nudi NON separano "stessa entita'" da "entita' diversa ma affine"
     ("direttore finanziario" vs "direttore commerciale" = 0.75 coseno).
  2. **giudizio** — un LLM decide se un candidato e' davvero la stessa entita'.
     Senza LLM si accetta solo la fascia quasi-certa (`AUTO_ACCEPT_*`), tutto
     il resto resta separato (un merge sbagliato corrompe il grafo, un merge
     mancato si recupera).

Tutto gira dentro la `canonical_session` del chiamante: la RLS limita la
ricerca al cliente corrente, quindi non si fondono mai entita' di clienti
diversi (INV-6).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.settings import settings

logger = logging.getLogger(__name__)

# --- soglie -------------------------------------------------------------
# Calibrate su embedding reali (text-embedding-3-small, 1536) di ~40 coppie
# di entita' di consulenza IT/finance. Risultato netto: coseno e trigram sui
# NOMI NUDI non separano "stessa entita'" da "entita' diversa ma affine"
# (SAME 0.45-0.84, DIFF 0.45-0.78). Quindi queste soglie generano CANDIDATI e
# la decisione la prende l'LLM; senza LLM si fonde solo il quasi-certo.
CANDIDATE_TRGM_MIN = 0.45
CANDIDATE_COSINE_MIN = 0.58
# Senza LLM: nella calibrazione nessuna coppia "entita' diverse" supera 0.78
# di coseno / 0.78 di trigram (i refusi arrivano a 0.87). Sopra queste si
# fonde direttamente.
AUTO_ACCEPT_COSINE = 0.88
AUTO_ACCEPT_TRGM = 0.82
# Quanti candidati passare all'LLM (ordinati per rilevanza).
MAX_CANDIDATES = 5

# entity_type != 'other' e' "specifico": non si fondono due tipi specifici
# diversi (una persona non e' un sistema). L'estrazione oggi emette sempre
# 'other', quindi il gate morde solo quando un tipo e' stato precisato a mano.
_OTHER = "other"


def normalize(name: str | None) -> str:
    """Chiave di confronto: whitespace collassato, casefold."""
    return " ".join(str(name or "").split()).casefold()


def _types_compatible(a: str, b: str) -> bool:
    return a == b or a == _OTHER or b == _OTHER


@dataclass
class Candidate:
    entity_id: str
    canonical_name: str
    entity_type: str
    aliases: list[str]
    cosine: float | None = None
    trgm: float | None = None

    def best_signal(self) -> float:
        return max(self.cosine or 0.0, self.trgm or 0.0)


@dataclass
class Match:
    entity_id: str
    canonical_name: str
    method: str  # exact_name | exact_alias | auto_cosine | auto_trgm | llm
    reason: str = ""


class _Verdict(BaseModel):
    """Schema del giudizio LLM (via with_structured_output)."""

    match_index: int = Field(
        default=0,
        description="Numero (1-based) del candidato che e' la stessa entita', 0 se nessuno.",
    )
    reason: str = Field(default="", description="Motivazione breve.")


# --------------------------------------------------------------------------- #
# lookup Postgres
# --------------------------------------------------------------------------- #


def _exact(
    session: Session, client_id: str, norm_name: str, entity_type: str
) -> Match | None:
    rows = session.execute(
        text(
            "SELECT id, canonical_name, entity_type, "
            "       lower(canonical_name) = :n AS name_hit "
            "FROM kg_entity "
            "WHERE client_id = :cl AND status <> 'rejected' "
            "  AND (lower(canonical_name) = :n OR aliases @> ARRAY[:n]) "
            # nome esatto prima dell'alias; poi tipo compatibile prima
            "ORDER BY name_hit DESC "
            "LIMIT 10"
        ),
        {"cl": client_id, "n": norm_name},
    ).all()
    for row in rows:
        if _types_compatible(entity_type, row.entity_type):
            return Match(
                entity_id=str(row.id),
                canonical_name=row.canonical_name,
                method="exact_name" if row.name_hit else "exact_alias",
            )
    return None


def _candidates(
    session: Session,
    client_id: str,
    norm_name: str,
    name_vec: str | None,
    entity_type: str,
) -> list[Candidate]:
    by_id: dict[str, Candidate] = {}

    trgm_rows = session.execute(
        text(
            "SELECT id, canonical_name, entity_type, aliases, "
            "       similarity(lower(canonical_name), :n) AS sim "
            "FROM kg_entity "
            "WHERE client_id = :cl AND status <> 'rejected' "
            "  AND lower(canonical_name) % :n "
            "ORDER BY sim DESC LIMIT 15"
        ),
        {"cl": client_id, "n": norm_name},
    ).all()
    for row in trgm_rows:
        if row.sim is None or float(row.sim) < CANDIDATE_TRGM_MIN:
            continue
        if not _types_compatible(entity_type, row.entity_type):
            continue
        by_id[str(row.id)] = Candidate(
            entity_id=str(row.id),
            canonical_name=row.canonical_name,
            entity_type=row.entity_type,
            aliases=list(row.aliases or []),
            trgm=float(row.sim),
        )

    if name_vec:
        vec_rows = session.execute(
            text(
                "SELECT id, canonical_name, entity_type, aliases, "
                "       1 - (embedding <=> CAST(:v AS vector)) AS cosine "
                "FROM kg_entity "
                "WHERE client_id = :cl AND status <> 'rejected' "
                "  AND embedding IS NOT NULL "
                "ORDER BY embedding <=> CAST(:v AS vector) LIMIT 15"
            ),
            {"cl": client_id, "v": name_vec},
        ).all()
        for row in vec_rows:
            cosine = float(row.cosine) if row.cosine is not None else 0.0
            if cosine < CANDIDATE_COSINE_MIN:
                continue
            if not _types_compatible(entity_type, row.entity_type):
                continue
            existing = by_id.get(str(row.id))
            if existing:
                existing.cosine = cosine
            else:
                by_id[str(row.id)] = Candidate(
                    entity_id=str(row.id),
                    canonical_name=row.canonical_name,
                    entity_type=row.entity_type,
                    aliases=list(row.aliases or []),
                    cosine=cosine,
                )

    ranked = sorted(by_id.values(), key=lambda c: c.best_signal(), reverse=True)
    return ranked[:MAX_CANDIDATES]


# --------------------------------------------------------------------------- #
# giudizio LLM
# --------------------------------------------------------------------------- #


def _build_prompt(
    name: str, entity_type: str, context: str | None, candidates: list[Candidate]
) -> list:
    from langchain_core.messages import HumanMessage, SystemMessage

    lines = [f"NUOVA ENTITA': {name!r} (tipo: {entity_type})"]
    if context:
        lines.append(f"Contesto in cui compare: {context.strip()[:500]}")
    lines.append("\nCANDIDATI gia' nel grafo:")
    for i, c in enumerate(candidates, start=1):
        alias = f", alias noti: {', '.join(c.aliases)}" if c.aliases else ""
        lines.append(f"  {i}. {c.canonical_name!r} (tipo: {c.entity_type}{alias})")
    lines.append(
        "\nQuale candidato e' LA STESSA entita' del mondo reale della nuova "
        "entita'? Rispondi con match_index = numero del candidato, oppure 0 se "
        "nessuno."
    )
    return [
        SystemMessage(
            content=(
                "Sei l'analista di un consulente di processo. Devi decidere "
                "l'IDENTITA' di due entita' di business, non la loro somiglianza. "
                "Stessa entita': sinonimi, sigla ed estesa ('CFO' = 'Chief "
                "Financial Officer'), traduzioni, varianti di scrittura, ruolo "
                "e persona che lo ricopre se chiaramente coincidono. Entita' "
                "DIVERSE: ruoli diversi della stessa area ('direttore "
                "finanziario' != 'direttore commerciale'), sistemi diversi, "
                "un ufficio e una persona che ci lavora, oggetti simili ma "
                "distinti ('ordine di vendita' != 'ordine di acquisto'). Nel "
                "dubbio, 0. Restituisci solo lo schema richiesto."
            )
        ),
        HumanMessage(content="\n".join(lines)),
    ]


def _adjudicate(
    llm: Any, name: str, entity_type: str, context: str | None, candidates: list[Candidate]
) -> Match | None:
    try:
        verdict = llm.invoke(_build_prompt(name, entity_type, context, candidates))
    except Exception:  # noqa: BLE001 — il resolver e' best-effort
        logger.warning("entity_resolution: giudizio LLM fallito", exc_info=True)
        return None

    idx = getattr(verdict, "match_index", 0)
    try:
        idx = int(idx)
    except (TypeError, ValueError):
        return None
    if not 1 <= idx <= len(candidates):
        return None
    chosen = candidates[idx - 1]
    return Match(
        entity_id=chosen.entity_id,
        canonical_name=chosen.canonical_name,
        method="llm",
        reason=str(getattr(verdict, "reason", "") or "")[:300],
    )


def _default_llm() -> Any | None:
    if not settings.openai_api_key:
        return None
    try:
        from langchain_openai import ChatOpenAI

        from backend.llm_config import chat_openai_kwargs

        return ChatOpenAI(**chat_openai_kwargs()).with_structured_output(_Verdict)
    except Exception:  # noqa: BLE001
        logger.warning("entity_resolution: LLM non inizializzabile", exc_info=True)
        return None


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #


def find_match(
    session: Session,
    *,
    client_id: str | None,
    entity_type: str,
    name: str,
    name_vec: str | None = None,
    context: str | None = None,
    llm: Any | None = None,
    use_llm: bool = True,
) -> Match | None:
    """L'entita' `name` esiste gia' per questo cliente? `Match` se si', `None` se no.

    `session` deve avere gia' il contesto RLS del cliente (la ricerca e' limitata
    a `client_id`). `name_vec` = embedding del nome nel literal pgvector
    (`embeddings.to_pgvector`), opzionale. `llm` iniettabile per i test; se
    `None` e `use_llm`, se ne costruisce uno dai settings.
    """
    if not client_id:
        return None  # lo scope consultant non ha ancora una chiave di dedup (P7)
    norm_name = normalize(name)
    if not norm_name:
        return None
    entity_type = (entity_type or _OTHER).strip().lower() or _OTHER

    exact = _exact(session, str(client_id), norm_name, entity_type)
    if exact:
        return exact

    candidates = _candidates(session, str(client_id), norm_name, name_vec, entity_type)
    if not candidates:
        return None

    top = candidates[0]
    if (top.cosine or 0.0) >= AUTO_ACCEPT_COSINE:
        return Match(top.entity_id, top.canonical_name, method="auto_cosine")
    if (top.trgm or 0.0) >= AUTO_ACCEPT_TRGM:
        return Match(top.entity_id, top.canonical_name, method="auto_trgm")

    model = llm if llm is not None else (_default_llm() if use_llm else None)
    if model is None:
        return None
    return _adjudicate(model, name, entity_type, context, candidates)
