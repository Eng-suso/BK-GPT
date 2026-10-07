"""I seed del retrieval: entita' nominate e chunk di testo, fusi con RRF.

Passi 1-3 di `graph_retrieve` (vedi il pacchetto): seed dalle entita' del
canonical, ricerca lessicale e vettoriale sui chunk, fusione dei ranking.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from backend.db import canonical_session
from backend.memory import embeddings
from backend.settings import settings
from backend.memory.gateway.scope import ReadScope, _WORD, _scope_sql, _source_provenance


def _resolve_seed_entities(
    consultant_id: str,
    scope: ReadScope,
    entity_names: list[str],
    query: str,
    source_ids: list[str] | None,
) -> list[str]:
    # lower() (non casefold) per coincidere con lower(canonical_name) di Postgres
    # e con gli alias, che entity_resolution salva gia' lower()
    terms = {" ".join(n.split()).lower() for n in entity_names if n and n.strip()}
    terms |= {w.lower() for w in _WORD.findall(query or "")}
    if not terms:
        return []
    exact = list(terms)
    like_patterns = [f"%{t}%" for t in terms]
    # Un'entita' entra come seed se ha provenance dentro lo scope, oppure se e'
    # stata scritta per questo processo/progetto (evidenza senza testo grezzo,
    # quindi senza kg_source). Il nome da solo non basta piu': due omonimi di
    # due processi diversi restano due entita' diverse.
    predicate, params = _scope_sql(scope)
    if scope.narrowed:
        predicate = (
            " AND (source_ids && CAST(:sc_sids AS uuid[])"
            f" OR ({predicate.removeprefix(' AND ')}))"
        )
        params = {**params, "sc_sids": list(source_ids or [])}
    with canonical_session(consultant_id, scope.client_id) as session:
        rows = session.execute(
            text(
                "SELECT id FROM kg_entity "
                "WHERE client_id = :cl AND status = 'active' "
                "  AND (lower(canonical_name) = ANY(:exact) "
                "       OR aliases && CAST(:exact AS text[]) "  # P2: alias noti
                "       OR lower(canonical_name) LIKE ANY(:like)) "
                + predicate +
                # match esatto (nome o alias) prima, poi nome piu' corto (piu'
                # probabilmente l'entita' precisa): da' un ranking vero alla RRF
                " ORDER BY (lower(canonical_name) = ANY(:exact) "
                "          OR aliases && CAST(:exact AS text[])) DESC, "
                "         char_length(canonical_name) "
                "LIMIT 40"
            ),
            {"cl": scope.client_id, "exact": exact, "like": like_patterns, **params},
        ).all()
    return [str(r.id) for r in rows]


def _rrf(ranked_lists: list[list[Any]], k: int = 60) -> list[tuple[Any, float]]:
    """Reciprocal Rank Fusion: piu' ranking -> un ordine unico con punteggio.

    Item hashable qualsiasi (entity_id str, oppure chiave chunk (source_id,
    ordinal)). Punteggio = somma di 1/(k + rank + 1) su ogni lista.
    """
    scores: dict[Any, float] = {}
    for lst in ranked_lists:
        for rank, item in enumerate(lst):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda kv: -kv[1])


@dataclass(frozen=True)
class ChunkHit:
    content: str
    source_id: str
    ordinal: int
    score: float  # RRF fuso
    lexical_score: float | None = None
    vector_score: float | None = None
    source_title: str = ""
    process_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        # La provenance viaggia col testo: un passaggio che finisce nel contesto
        # dell'agente deve poter essere ricondotto alla fonte e al processo da
        # cui viene, altrimenti nessuno puo' verificarlo a valle.
        return {
            "content": self.content,
            "score": round(self.score, 6),
            "lexical_score": self.lexical_score,
            "vector_score": self.vector_score,
            "source_id": self.source_id,
            "source_title": self.source_title,
            "process_id": self.process_id,
        }


@dataclass(frozen=True)
class ChunkSearch:
    entity_ids: tuple[str, ...]  # entita' da provenance, ordinate per rank chunk
    chunks: tuple[ChunkHit, ...]


_EMPTY_CHUNK_SEARCH = ChunkSearch(entity_ids=(), chunks=())


def _text_search(
    consultant_id: str,
    scope: ReadScope,
    query: str,
    k: int,
    source_ids: list[str] | None,
) -> ChunkSearch:
    """Ricerca ibrida sui `kg_chunk`: lessicale (`ts_rank_cd`) + vettoriale
    (cosine), fusi con RRF. Dai chunk fusi si risale alle entita' con quella
    provenance, ordinate per rank del loro miglior chunk.

    I chunk cercabili sono solo quelli delle `kg_source` autorizzate
    (`source_ids`): il testo grezzo di un'altra intervista dello stesso cliente
    non deve poter entrare nel contesto per somiglianza semantica.

    Degrada: senza embedder -> solo lessicale; senza match -> vuoto.
    """
    if not (query or "").strip():
        return _EMPTY_CHUNK_SEARCH
    if source_ids is not None and not source_ids:
        return _EMPTY_CHUNK_SEARCH  # scope senza fonti: fail closed, non client-wide
    client_id = scope.client_id

    # tsquery OR-of-terms: recall lessicale (qualsiasi parola), ranking a
    # `ts_rank_cd`. I termini vengono dal regex `_WORD` (solo caratteri di
    # parola) quindi sono gia' sicuri per `to_tsquery`.
    lex_terms = list(dict.fromkeys(w.lower() for w in _WORD.findall(query or "")))
    tsquery = " | ".join(lex_terms)

    # `kg_chunk` non porta process_id: la provenance del chunk e' la sua
    # `kg_source`, che invece lo porta. Il confine passa quindi dall'elenco di
    # fonti autorizzate, non da una colonna del chunk.
    scoped = "" if source_ids is None else " AND source_id = ANY(CAST(:sids AS uuid[]))"
    scope_params: dict[str, Any] = {} if source_ids is None else {"sids": list(source_ids)}

    with canonical_session(consultant_id, client_id) as session:
        if not session.execute(
            text("SELECT 1 FROM kg_chunk WHERE client_id = :cl LIMIT 1" ),
            {"cl": client_id},
        ).first():
            return _EMPTY_CHUNK_SEARCH

        lex_rows: list[Any] = []
        if tsquery:
            lex_rows = session.execute(
                text(
                    "SELECT source_id, ordinal, content, "
                    "       ts_rank_cd(content_tsv, q) AS score "
                    "FROM kg_chunk, to_tsquery('simple', :tsq) AS q "
                    "WHERE client_id = :cl AND content_tsv @@ q "
                    + scoped +
                    " ORDER BY score DESC LIMIT :k"
                ),
                {"cl": client_id, "tsq": tsquery, "k": k, **scope_params},
            ).all()

        vec_rows: list[Any] = []
        vec = embeddings.embed_query(query) if embeddings.available() else None
        if vec is not None:
            vec_rows = session.execute(
                text(
                    "SELECT source_id, ordinal, content, "
                    "       1 - (embedding <=> CAST(:q AS vector)) AS score "
                    "FROM kg_chunk "
                    "WHERE client_id = :cl AND embedding IS NOT NULL "
                    + scoped +
                    " ORDER BY embedding <=> CAST(:q AS vector) LIMIT :k"
                ),
                {"q": embeddings.to_pgvector(vec), "cl": client_id, "k": k, **scope_params},
            ).all()

        if not lex_rows and not vec_rows:
            return _EMPTY_CHUNK_SEARCH

        def _key(row: Any) -> tuple[str, int]:
            return (str(row.source_id), int(row.ordinal))

        lexical_by_key = {_key(r): float(r.score) for r in lex_rows}
        vector_by_key = {_key(r): float(r.score) for r in vec_rows}
        content_by_key = {_key(r): r.content for r in (*lex_rows, *vec_rows)}

        fused = _rrf([[_key(r) for r in lex_rows], [_key(r) for r in vec_rows]])
        provenance = _source_provenance(
            session, client_id, {key[0] for key, _ in fused[:k]}
        )
        chunks = tuple(
            ChunkHit(
                content=content_by_key[key],
                source_id=key[0],
                ordinal=key[1],
                score=rrf,
                lexical_score=lexical_by_key.get(key),
                vector_score=vector_by_key.get(key),
                source_title=provenance.get(key[0], ("", None))[0],
                process_id=provenance.get(key[0], ("", None))[1],
            )
            for key, rrf in fused[:k]
        )

        # entita' con quella provenance, ordinate per il rank del loro miglior chunk
        source_rank: dict[str, int] = {}
        for rank, (key, _score) in enumerate(fused):
            source_rank.setdefault(key[0], rank)
        ent_rows = session.execute(
            text(
                "SELECT id, source_ids FROM kg_entity "
                "WHERE client_id = :cl AND status = 'active' "
                "  AND source_ids && CAST(:sids AS uuid[])"
            ),
            {"cl": client_id, "sids": list(source_rank)},
        ).all()

    def _entity_rank(row: Any) -> int:
        return min(
            (source_rank[str(s)] for s in row.source_ids if str(s) in source_rank),
            default=len(source_rank),
        )

    entity_ids = tuple(
        str(r.id) for r in sorted(ent_rows, key=_entity_rank)
    )
    return ChunkSearch(entity_ids=entity_ids, chunks=chunks)


def _context_chunks(query: str, text_hit: ChunkSearch) -> list[dict[str, Any]]:
    """Chunk di contesto per l'agente: fusi RRF (`_text_search`), poi rerank
    LLM opzionale (`settings.retrieval_rerank_enabled`, default off)."""
    chunks = [c.as_dict() for c in text_hit.chunks]
    if not chunks or not settings.retrieval_rerank_enabled:
        return chunks
    from backend.memory import reranker

    return reranker.rerank_passages(query, chunks, key="content")
