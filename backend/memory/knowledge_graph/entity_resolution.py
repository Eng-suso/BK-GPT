"""Entity resolution (P2): "questa entita' e' gia' nel grafo?".

Prima di scrivere una `kg_entity`, il writer chiede qui se il nome che sta per
inserire e' la stessa cosa del mondo reale di un'entita' gia' nota per quel
cliente. Se si', il writer aggiorna l'entita' esistente (alias + provenance)
invece di crearne una seconda.

Tre livelli, dal piu' certo al piu' incerto:

  0. **esatto** — `canonical_name` o un `alias` coincide (whitespace + `lower()`,
     stessa normalizzazione di Postgres). Deciso senza LLM.
  1. **candidati** — nomi lessicalmente simili (`pg_trgm`) o semanticamente
     vicini (coseno su `kg_entity.embedding`). SOLO recall: la calibrazione su
     embedding reali mostra che coseno e trigram sui nomi nudi non decidono
     l'identita' — "direttore finanziario" vs "direttore commerciale" = 0.75
     coseno, "Segreto A" vs "Segreto B" = 0.92.
  2. **giudizio** — un LLM (`temperature=0`, `with_structured_output`) decide
     l'identita'. Nessuna soglia fonde da sola. Senza LLM il resolver si ferma
     al livello 0: un merge sbagliato corrompe il grafo, un merge mancato si
     recupera con lo sweep periodico (`scripts/kg_resolve_entities.py`).

**Confine LLM/runtime.** L'LLM propone (`Match`), il runtime dispone: applicare
il piano e' UPSERT deterministico in `canonical.write_entity`. `plan_resolution`
lavora in due fasi: (1) `shortlist` fa il lookup deterministico di TUTTI i nomi
in una `canonical_session` read-only, poi la sessione si CHIUDE; (2) `decide`
fa il giudizio LLM sui nomi incerti, con nessuna connessione DB aperta. Mai una
chiamata di rete mentre si tiene un lock o uno snapshot. La RLS della sessione
limita la ricerca al cliente corrente: mai merge cross-client (INV-6).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.db import canonical_session
from backend.memory import embeddings
from backend.services import degradation_counters
from backend.settings import settings

logger = logging.getLogger(__name__)

# --- soglie -------------------------------------------------------------
# Calibrate su embedding reali (text-embedding-3-small, 1536) di ~40 coppie di
# entita' di consulenza IT/finance. Risultato netto: coseno e trigram sui NOMI
# NUDI NON decidono l'identita'. Non solo SAME (0.45-0.84) e DIFF (0.45-0.78)
# si sovrappongono: coppie palesemente distinte che differiscono per un token
# discriminante ("Segreto A" / "Segreto B") arrivano a 0.92 di coseno. Nessuna
# soglia di auto-merge e' sicura -> ogni candidato fuzzy passa dall'LLM.
CANDIDATE_TRGM_MIN = 0.45
CANDIDATE_COSINE_MIN = 0.58
# Quanti candidati passare all'LLM (ordinati per rilevanza).
MAX_CANDIDATES = 5

# entity_type != 'other' e' "specifico": non si fondono due tipi specifici
# diversi (una persona non e' un sistema). L'estrazione oggi emette sempre
# 'other', quindi il gate morde solo quando un tipo e' stato precisato a mano.
_OTHER = "other"

# uuid "nil": placeholder per "non escludere nessuna riga" (evita il parametro
# non tipizzato di `:x IS NULL` in psycopg).
_NIL_UUID = "00000000-0000-0000-0000-000000000000"

MatchMethod = Literal["exact_name", "exact_alias", "llm"]


def normalize(name: str | None) -> str:
    """Chiave di confronto: whitespace collassato + `lower()`.

    `lower()` (non `casefold()`) per coincidere esattamente con `lower(...)` di
    Postgres usato nelle query di `_exact` / `_candidates`.
    """
    return " ".join(str(name or "").split()).lower()


def types_compatible(a: str | None, b: str | None) -> bool:
    """Due tipi si possono fondere? Si' se uguali o se almeno uno e' 'other'."""
    a, b = (a or _OTHER).lower(), (b or _OTHER).lower()
    return a == b or _OTHER in (a, b)


@dataclass(frozen=True)
class Candidate:
    entity_id: str
    canonical_name: str
    entity_type: str
    aliases: tuple[str, ...] = ()
    cosine: float | None = None
    trgm: float | None = None

    def best_signal(self) -> float:
        return max(self.cosine or 0.0, self.trgm or 0.0)


@dataclass(frozen=True)
class Match:
    """Decisione del resolver: `name` e' l'entita' `entity_id`."""

    entity_id: str
    canonical_name: str
    method: MatchMethod
    reason: str = ""


@dataclass(frozen=True)
class ResolvedEntity:
    entity_id: str
    canonical_name: str
    method: MatchMethod


@dataclass(frozen=True)
class ResolutionPlan:
    """Esito di `plan_resolution`, calcolato FUORI dalla transazione di scrittura.

    `matches`: `normalize(name) -> ResolvedEntity` per i nomi gia' rappresentati
    da una riga esistente. `name_vectors`: `normalize(name) -> literal pgvector`
    dell'embedding del nome, per popolare `kg_entity.embedding` sui nuovi insert.
    """

    matches: Mapping[str, ResolvedEntity] = field(default_factory=dict)
    name_vectors: Mapping[str, str | None] = field(default_factory=dict)

    def lookup(self, raw_name: str) -> tuple[ResolvedEntity | None, str | None]:
        key = normalize(raw_name)
        return self.matches.get(key), self.name_vectors.get(key)


EMPTY_PLAN = ResolutionPlan()


class _Verdict(BaseModel):
    """Schema del giudizio LLM (trust boundary -> Pydantic)."""

    match_index: int = Field(
        default=0,
        description="Numero (1-based) del candidato che e' la stessa entita', 0 se nessuno.",
    )
    reason: str = Field(default="", description="Motivazione breve.")


# --------------------------------------------------------------------------- #
# lookup Postgres (deterministico)
# --------------------------------------------------------------------------- #


def _exact(
    session: Session,
    client_id: str,
    norm_name: str,
    entity_type: str,
    exclude_id: str | None,
) -> Match | None:
    rows = session.execute(
        text(
            "SELECT id, canonical_name, entity_type, "
            "       lower(canonical_name) = :n AS name_hit "
            "FROM kg_entity "
            "WHERE client_id = :cl AND status = 'active' "
            "  AND id <> CAST(:excl AS uuid) "
            "  AND (lower(canonical_name) = :n OR aliases @> ARRAY[:n]) "
            # nome esatto prima dell'alias
            "ORDER BY name_hit DESC "
            "LIMIT 10"
        ),
        {"cl": client_id, "n": norm_name, "excl": exclude_id or _NIL_UUID},
    ).all()
    for row in rows:
        if types_compatible(entity_type, row.entity_type):
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
    exclude_id: str | None = None,
) -> list[Candidate]:
    by_id: dict[str, Candidate] = {}
    common = {"cl": client_id, "n": norm_name, "excl": exclude_id or _NIL_UUID}
    not_self = "AND id <> CAST(:excl AS uuid) "

    trgm_rows = session.execute(
        text(
            "SELECT id, canonical_name, entity_type, aliases, "
            "       similarity(lower(canonical_name), :n) AS sim "
            "FROM kg_entity "
            "WHERE client_id = :cl AND status = 'active' "
            f"  {not_self}"
            "  AND lower(canonical_name) % :n "
            "ORDER BY sim DESC LIMIT 15"
        ),
        common,
    ).all()
    for row in trgm_rows:
        if row.sim is None or float(row.sim) < CANDIDATE_TRGM_MIN:
            continue
        if not types_compatible(entity_type, row.entity_type):
            continue
        by_id[str(row.id)] = Candidate(
            entity_id=str(row.id),
            canonical_name=row.canonical_name,
            entity_type=row.entity_type,
            aliases=tuple(row.aliases or ()),
            trgm=float(row.sim),
        )

    if name_vec:
        vec_rows = session.execute(
            text(
                "SELECT id, canonical_name, entity_type, aliases, "
                "       1 - (embedding <=> CAST(:v AS vector)) AS cosine "
                "FROM kg_entity "
                "WHERE client_id = :cl AND status = 'active' "
                f"  {not_self}"
                "  AND embedding IS NOT NULL "
                "ORDER BY embedding <=> CAST(:v AS vector) LIMIT 15"
            ),
            {**common, "v": name_vec},
        ).all()
        for row in vec_rows:
            cosine = float(row.cosine) if row.cosine is not None else 0.0
            if cosine < CANDIDATE_COSINE_MIN:
                continue
            if not types_compatible(entity_type, row.entity_type):
                continue
            prev = by_id.get(str(row.id))
            if prev is not None:
                by_id[str(row.id)] = Candidate(
                    entity_id=prev.entity_id,
                    canonical_name=prev.canonical_name,
                    entity_type=prev.entity_type,
                    aliases=prev.aliases,
                    cosine=cosine,
                    trgm=prev.trgm,
                )
            else:
                by_id[str(row.id)] = Candidate(
                    entity_id=str(row.id),
                    canonical_name=row.canonical_name,
                    entity_type=row.entity_type,
                    aliases=tuple(row.aliases or ()),
                    cosine=cosine,
                )

    return sorted(by_id.values(), key=lambda c: c.best_signal(), reverse=True)[:MAX_CANDIDATES]


# --------------------------------------------------------------------------- #
# giudizio LLM (semantico)
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


def _coerce_verdict(raw: object) -> _Verdict | None:
    """Output dell'LLM (untrusted) -> `_Verdict` validato, o `None` se non lo e'."""
    if isinstance(raw, _Verdict):
        return raw
    if isinstance(raw, Mapping):
        try:
            return _Verdict.model_validate(dict(raw))
        except Exception:  # noqa: BLE001 — forma inattesa: model-behavior error
            pass
    logger.warning(
        "entity_resolution: verdetto LLM non validabile (%s)", type(raw).__name__
    )
    return None


def adjudicate(
    llm: Any,
    name: str,
    entity_type: str,
    context: str | None,
    candidates: list[Candidate],
) -> Match | None:
    if not candidates:
        return None
    try:
        raw = llm.invoke(_build_prompt(name, entity_type, context, candidates))
    except Exception as exc:  # noqa: BLE001 — il resolver e' best-effort, mai fatale
        # merge fuzzy saltato: si crea una nuova entita', il merge mancato si
        # recupera con lo sweep. Ma va reso visibile: un LLM giu' = il grafo
        # accumula duplicati in silenzio.
        degradation_counters.bump("entity_resolution", "llm_failed", detail=str(exc))
        return None

    verdict = _coerce_verdict(raw)
    if verdict is None or not 1 <= verdict.match_index <= len(candidates):
        return None
    chosen = candidates[verdict.match_index - 1]
    return Match(
        entity_id=chosen.entity_id,
        canonical_name=chosen.canonical_name,
        method="llm",
        reason=verdict.reason[:300],
    )


_llm_singleton: Any | None = None


def build_llm() -> Any | None:
    """Costruisce (una volta) il client LLM del resolver.

    Non usa `lru_cache`: un fallimento *transitorio* di init non deve restare
    inchiodato per tutta la vita del processo. Il successo e' memoizzato; il
    caso "nessuna api key" e' economico da ricontrollare.
    """
    global _llm_singleton
    if _llm_singleton is not None:
        return _llm_singleton
    if not settings.openai_api_key:
        return None
    try:
        from langchain_openai import ChatOpenAI

        from backend.llm_config import chat_openai_kwargs

        _llm_singleton = ChatOpenAI(**chat_openai_kwargs()).with_structured_output(_Verdict)
        return _llm_singleton
    except Exception as exc:  # noqa: BLE001
        degradation_counters.bump("entity_resolution", "llm_init_failed", detail=str(exc))
        return None


# --------------------------------------------------------------------------- #
# API — lookup (in sessione) e giudizio (senza DB), separati di proposito
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Shortlist:
    """Esito del lookup deterministico, PRIMA del giudizio LLM.

    `exact` valorizzato -> deciso (nessun LLM). Altrimenti `candidates` sono i
    profili da passare all'LLM. Non contiene riferimenti alla sessione: si puo'
    chiudere la `canonical_session` e poi chiamare `decide`.
    """

    exact: Match | None
    candidates: tuple[Candidate, ...]

    @property
    def needs_llm(self) -> bool:
        return self.exact is None and bool(self.candidates)


_EMPTY_SHORTLIST = Shortlist(exact=None, candidates=())


def shortlist(
    session: Session,
    *,
    client_id: str | None,
    entity_type: str,
    name: str,
    name_vec: str | None = None,
    exclude_entity_id: str | None = None,
) -> Shortlist:
    """Lookup deterministico per un nome (match esatto + candidati fuzzy).

    Tutto qui tocca il DB; nient'altro nel modulo. `session` deve avere gia' il
    contesto RLS del cliente.
    """
    if not client_id:
        return _EMPTY_SHORTLIST
    norm_name = normalize(name)
    if not norm_name:
        return _EMPTY_SHORTLIST
    etype = (entity_type or _OTHER).strip().lower() or _OTHER

    exact = _exact(session, str(client_id), norm_name, etype, exclude_entity_id)
    if exact is not None:
        return Shortlist(exact=exact, candidates=())
    candidates = _candidates(
        session, str(client_id), norm_name, name_vec, etype, exclude_entity_id
    )
    return Shortlist(exact=None, candidates=tuple(candidates))


def decide(
    sl: Shortlist,
    *,
    name: str,
    entity_type: str = _OTHER,
    context: str | None = None,
    llm: Any | None = None,
) -> Match | None:
    """Dalla `Shortlist` alla decisione. Nessun accesso al DB: solo (eventuale)
    chiamata LLM. `llm` None -> nessun merge fuzzy (solo il match esatto)."""
    if sl.exact is not None:
        return sl.exact
    if llm is None or not sl.candidates:
        return None
    return adjudicate(
        llm, name, (entity_type or _OTHER).strip().lower() or _OTHER, context, list(sl.candidates)
    )


def find_match(
    session: Session,
    *,
    client_id: str | None,
    entity_type: str,
    name: str,
    name_vec: str | None = None,
    context: str | None = None,
    exclude_entity_id: str | None = None,
    llm: Any | None = None,
    use_llm: bool = True,
) -> Match | None:
    """Lookup + giudizio in un colpo solo, per una singola entita' (test, chiamate
    puntuali). Per un batch usare `plan_resolution` (chiude la sessione prima
    dell'LLM). Il giudizio qui avviene con la `session` del chiamante aperta.
    """
    sl = shortlist(
        session,
        client_id=client_id,
        entity_type=entity_type,
        name=name,
        name_vec=name_vec,
        exclude_entity_id=exclude_entity_id,
    )
    model = llm if llm is not None else (build_llm() if use_llm else None)
    return decide(sl, name=name, entity_type=entity_type, context=context, llm=model)


def _embed_names(display_names: list[str]) -> dict[str, str]:
    """`display_name -> literal pgvector`. Vuoto se l'embedder non e' disponibile."""
    vectors = embeddings.embed_texts(display_names)
    if not vectors:
        return {}
    out: dict[str, str] = {}
    for name, vec in zip(display_names, vectors):
        literal = embeddings.to_pgvector(vec)
        if literal is not None:
            out[name] = literal
    return out


def plan_resolution(
    consultant_id: str,
    client_id: str | None,
    names: Iterable[str | None],
    *,
    context: str | None = None,
    llm: Any | None = None,
) -> ResolutionPlan:
    """Risolve un insieme di nomi entita' PRIMA della transazione di scrittura.

    (1) lookup deterministico di TUTTI i nomi in una `canonical_session`
    read-only, poi la sessione si CHIUDE; (2) giudizio LLM sui nomi rimasti
    incerti, senza alcuna connessione DB aperta. Nessuna chiamata di rete
    mentre si tiene un lock o uno snapshot. No-op (piano vuoto) senza cliente o
    con `settings.canonical_entity_resolution` a False.
    """
    if not client_id or not settings.canonical_entity_resolution:
        return EMPTY_PLAN

    uniq: dict[str, str] = {}
    for raw in names:
        key = normalize(raw)
        if key and key not in uniq:
            uniq[key] = " ".join(str(raw).split())
    if not uniq:
        return EMPTY_PLAN

    vec_by_display = _embed_names(list(uniq.values()))
    name_vectors = {key: vec_by_display.get(display) for key, display in uniq.items()}

    try:
        # (1) lookup — in sessione
        with canonical_session(consultant_id, client_id) as session:
            shortlisted = {
                key: shortlist(
                    session,
                    client_id=client_id,
                    entity_type=_OTHER,
                    name=display,
                    name_vec=name_vectors.get(key),
                )
                for key, display in uniq.items()
            }

        # (2) giudizio — nessuna connessione DB aperta
        model = llm if llm is not None else build_llm()
        matches: dict[str, ResolvedEntity] = {}
        for key, sl in shortlisted.items():
            hit = decide(sl, name=uniq[key], entity_type=_OTHER, context=context, llm=model)
            if hit is not None:
                matches[key] = ResolvedEntity(hit.entity_id, hit.canonical_name, hit.method)
                logger.info(
                    "entity resolution: %r -> %r (%s)",
                    uniq[key], hit.canonical_name, hit.method,
                )
    except Exception as exc:  # noqa: BLE001
        # La resolution e' best-effort (INV: merge mancato -> sweep). Un suo
        # errore (pg_trgm assente, DB, embedder) NON deve far perdere l'intero
        # pacchetto di evidenza: si degrada a "nessun match", il write procede.
        degradation_counters.bump("entity_resolution", "plan_failed", detail=str(exc))
        return ResolutionPlan(matches={}, name_vectors=name_vectors)

    return ResolutionPlan(matches=matches, name_vectors=name_vectors)
