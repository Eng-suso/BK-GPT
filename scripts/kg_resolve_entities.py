"""Backfill embedding + sweep di deduplica su `kg_entity` (P2).

Il resolver in scrittura (`entity_resolution.find_match`) evita i doppioni man
mano che l'evidenza entra: match esatto nome/alias -> shortlist trigram/coseno
-> **giudizio LLM** (temperature 0, structured output). Nessuna soglia fonde da
sola. Questo script applica la stessa identica logica in due modi:

  1. **backfill** — popola `kg_entity.embedding` sulle righe che non ce l'hanno
     (entita' scritte prima di P2 o con l'embedder giu');
  2. **sweep** — per ogni entita' `active` chiede a `find_match` (escludendo se
     stessa) se e' gia' rappresentata da un'altra riga; se si', FONDE: la piu'
     recente confluisce nella piu' vecchia (alias + provenance + relazioni
     ripuntate), la piu' recente diventa `deprecated` e sparisce da Neo4j via
     l'outbox.

Gira come `delir_app` (`CANONICAL_DATABASE_URL`), stesso percorso RLS della
produzione. Mono-consultant: `--consultant` o `settings.default_consultant_id`.

    CANONICAL_DATABASE_URL=... OPENAI_API_KEY=... \
      uv run python -m scripts.kg_resolve_entities              # dry-run
    ... uv run python -m scripts.kg_resolve_entities --apply
    ... uv run python -m scripts.kg_resolve_entities --client <uuid> --apply
    ... uv run python -m scripts.kg_resolve_entities --no-sweep # solo backfill

Senza `--apply` non scrive nulla: elenca solo le fusioni che farebbe.
"""

from __future__ import annotations

import argparse
import json
import logging
import secrets
import sys
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.db import canonical_session
from backend.memory import embeddings
from backend.memory.knowledge_graph import entity_resolution as er
from backend.settings import settings

logger = logging.getLogger("kg_resolve_entities")

_EMBED_BATCH = 256


@dataclass
class Stats:
    backfilled: int = 0
    merges: int = 0


# --------------------------------------------------------------------------- #
# backfill embedding
# --------------------------------------------------------------------------- #


def backfill_client(consultant: str, client: str, apply: bool) -> int:
    """Embedda i nomi delle `kg_entity` senza `embedding`. Idempotente
    (`WHERE embedding IS NULL`): un batch che fallisce si rifa'. Commit per
    batch (transazione dedicata) per non tenere aperto tutto il cliente."""
    with canonical_session(consultant, client) as reader:
        rows = reader.execute(
            text(
                "SELECT id, canonical_name FROM kg_entity "
                "WHERE client_id = :cl AND status <> 'rejected' AND embedding IS NULL "
                "ORDER BY created_at"
            ),
            {"cl": client},
        ).all()
    if not rows:
        return 0
    if not embeddings.available():
        logger.warning("  backfill saltato: OPENAI_API_KEY assente (%d righe)", len(rows))
        return 0
    if not apply:
        print(f"  [dry-run] backfill embedding: {len(rows)} entita'")
        return len(rows)

    done = 0
    for start in range(0, len(rows), _EMBED_BATCH):
        batch = rows[start : start + _EMBED_BATCH]
        vectors = embeddings.embed_texts([r.canonical_name for r in batch])
        if not vectors:
            logger.warning("  embed_texts ha reso None: batch saltato")
            continue
        with canonical_session(consultant, client) as writer:
            for row, vec in zip(batch, vectors):
                writer.execute(
                    text(
                        "UPDATE kg_entity SET embedding = CAST(:e AS vector), "
                        "  embed_model = :m, embed_dim = :d, embed_version = :v "
                        "WHERE id = :i AND embedding IS NULL"
                    ),
                    {
                        "e": embeddings.to_pgvector(vec),
                        "m": embeddings.EMBED_MODEL,
                        "d": embeddings.EMBED_DIM,
                        "v": embeddings.EMBED_VERSION,
                        "i": row.id,
                    },
                )
                done += 1
    print(f"  backfill embedding: {done} entita'")
    return done


# --------------------------------------------------------------------------- #
# merge di due righe kg_entity gia' esistenti
# --------------------------------------------------------------------------- #

_LOSER_RELS = (
    "SELECT id, source_entity_id, target_entity_id, relation, confidence, confirmed, "
    "       source_ids "
    "FROM kg_relation "
    "WHERE client_id = :cl AND status <> 'rejected' "
    "  AND (source_entity_id = :lo OR target_entity_id = :lo)"
)
_FIND_TWIN = (
    "SELECT id FROM kg_relation "
    "WHERE client_id = :cl AND status <> 'rejected' "
    "  AND source_entity_id = :ns AND target_entity_id = :nt "
    "  AND relation = :rel AND id <> :self"
)
_FOLD_TWIN = (
    "UPDATE kg_relation SET "
    "  confidence = GREATEST(confidence, :c), "
    "  confirmed = confirmed OR :cf, "
    "  source_ids = COALESCE((SELECT array_agg(DISTINCT x) "
    "     FROM unnest(source_ids || CAST(:src AS uuid[])) x), source_ids) "
    "WHERE id = :i"
)


def _repoint_one(session: Session, client: str, rel, ns: str, nt: str) -> None:
    """Sposta una relazione del loser sul survivor. Tre esiti, senza annidamento."""
    if ns == nt:
        session.execute(text("DELETE FROM kg_relation WHERE id = :i"), {"i": rel.id})
        return
    twin = session.execute(
        text(_FIND_TWIN),
        {"cl": client, "ns": ns, "nt": nt, "rel": rel.relation, "self": rel.id},
    ).first()
    if twin is None:
        session.execute(
            text(
                "UPDATE kg_relation SET source_entity_id = :ns, target_entity_id = :nt "
                "WHERE id = :i"
            ),
            {"ns": ns, "nt": nt, "i": rel.id},
        )
        return
    session.execute(
        text(_FOLD_TWIN),
        {
            "c": rel.confidence,
            "cf": rel.confirmed,
            "src": [str(x) for x in (rel.source_ids or [])],
            "i": twin.id,
        },
    )
    session.execute(text("DELETE FROM kg_relation WHERE id = :i"), {"i": rel.id})


def _emit(session: Session, *, agg_type: str, agg_id: str, consultant: str,
          client: str, payload: dict, op: str = "upsert") -> None:
    session.execute(
        text(
            "INSERT INTO graph_outbox "
            "(aggregate_type, aggregate_id, consultant_id, client_id, op, payload, dedupe_key) "
            "VALUES (:at,:aid,:c,:cl,:op, CAST(:p AS jsonb), :dk)"
        ),
        {
            "at": agg_type, "aid": agg_id, "c": consultant, "cl": client, "op": op,
            "p": json.dumps(payload, default=str, sort_keys=True),
            "dk": f"{agg_type}:{agg_id}:{secrets.token_hex(8)}",
        },
    )


def merge_entities(
    session: Session, consultant: str, client: str, survivor: str, loser: str
) -> None:
    # 1. il survivor assorbe dal loser: nome+alias, provenance (source_ids),
    #    attributi (il survivor vince sui conflitti di chiave), confidence, e
    #    l'embedding se non ne ha (riga pre-P2). Stesso merge del write path
    #    (_MERGE_ENTITY in canonical.py).
    session.execute(
        text(
            "UPDATE kg_entity sv SET "
            "  aliases = COALESCE((("
            "    SELECT array_agg(DISTINCT a) FROM unnest("
            "      sv.aliases || ARRAY[lower(lo.canonical_name)] || lo.aliases) AS a "
            "    WHERE a <> lower(sv.canonical_name) AND a <> ''"
            "  )), sv.aliases), "
            "  source_ids = COALESCE((SELECT array_agg(DISTINCT x) FROM unnest("
            "    sv.source_ids || lo.source_ids) AS x), sv.source_ids), "
            "  attributes = lo.attributes || sv.attributes, "
            "  confidence = GREATEST(sv.confidence, lo.confidence), "
            "  embedding = COALESCE(sv.embedding, lo.embedding), "
            "  embed_model = COALESCE(sv.embed_model, lo.embed_model), "
            "  embed_dim = COALESCE(sv.embed_dim, lo.embed_dim), "
            "  embed_version = COALESCE(sv.embed_version, lo.embed_version) "
            "FROM kg_entity lo WHERE sv.id = :sv AND lo.id = :lo"
        ),
        {"sv": survivor, "lo": loser},
    )
    # 2. relazioni del loser ripuntate sul survivor
    for rel in session.execute(text(_LOSER_RELS), {"cl": client, "lo": loser}).all():
        ns = survivor if str(rel.source_entity_id) == loser else str(rel.source_entity_id)
        nt = survivor if str(rel.target_entity_id) == loser else str(rel.target_entity_id)
        _repoint_one(session, client, rel, ns, nt)
    # 3. loser deprecato. convenzione kg_entity: la riga deprecata punta via
    #    supersedes_id alla riga che l'ha assorbita (opposto di procedural_memory).
    session.execute(
        text("UPDATE kg_entity SET status = 'deprecated', supersedes_id = :sv WHERE id = :lo"),
        {"sv": survivor, "lo": loser},
    )
    # 4. Neo4j via outbox: cancella il nodo loser (DETACH DELETE porta via i suoi
    #    archi), poi rifa' gli archi che ora toccano il survivor.
    _emit(
        session, agg_type="entity", agg_id=loser, consultant=consultant, client=client,
        op="delete",
        payload={"kind": "node_delete", "label": "Entity",
                 "id_prop": "entity_id", "id_value": loser},
    )
    survivor_rels = session.execute(
        text(
            "SELECT id, source_entity_id, target_entity_id, relation, confidence, "
            "       confirmed, project_id FROM kg_relation "
            "WHERE client_id = :cl AND status = 'active' "
            "  AND (source_entity_id = :sv OR target_entity_id = :sv)"
        ),
        {"cl": client, "sv": survivor},
    ).all()
    for r in survivor_rels:
        _emit(
            session, agg_type="relation", agg_id=str(r.id), consultant=consultant,
            client=client,
            payload={
                "kind": "edge", "label": r.relation,
                "source": {"label": "Entity", "id_prop": "entity_id",
                           "id_value": str(r.source_entity_id)},
                "target": {"label": "Entity", "id_prop": "entity_id",
                           "id_value": str(r.target_entity_id)},
                "props": {
                    "relation_id": str(r.id), "client_id": client,
                    "project_id": str(r.project_id) if r.project_id else None,
                    "layer": "L1", "status": "active",
                    "confidence": float(r.confidence), "confirmed": bool(r.confirmed),
                },
            },
        )


# --------------------------------------------------------------------------- #
# sweep
# --------------------------------------------------------------------------- #


_ACTIVE_ENTITIES = (
    "SELECT id, canonical_name, entity_type, created_at, embedding::text AS emb "
    "FROM kg_entity WHERE client_id = :cl AND status = 'active' "
    "ORDER BY created_at DESC"  # la piu' recente confluisce nella piu' vecchia
)


def sweep_client(
    consultant: str, client: str, llm: Any, apply: bool, limit: int
) -> int:
    """Fase 1: snapshot + lookup deterministico di ogni entita' in una sessione
    read-only, poi la chiude. Fase 2: giudizio LLM (nessuna connessione aperta)
    e, per ogni merge deciso, una transazione dedicata (`merge_entities` e'
    atomico: entita' + relazioni + outbox o niente). Un crash a meta' lascia i
    merge gia' fatti committati.
    """
    with canonical_session(consultant, client) as reader:
        ents = reader.execute(text(_ACTIVE_ENTITIES), {"cl": client}).all()
        if len(ents) < 2:
            return 0
        shortlisted = [
            (
                e,
                er.shortlist(
                    reader,
                    client_id=client,
                    entity_type=e.entity_type or "other",
                    name=e.canonical_name,
                    name_vec=e.emb,
                    exclude_entity_id=str(e.id),
                ),
            )
            for e in ents
        ]

    born = {str(e.id): e.created_at for e in ents}
    name_of = {str(e.id): e.canonical_name for e in ents}
    # loser_id -> survivor_id: tiene la catena (A->B, poi C che matcha B) anche
    # in dry-run, dove nessuna riga cambia stato.
    absorbed_by: dict[str, str] = {}

    def _survivor(entity_id: str) -> str:
        seen: set[str] = set()
        while entity_id in absorbed_by and entity_id not in seen:
            seen.add(entity_id)
            entity_id = absorbed_by[entity_id]
        return entity_id

    n_merges = 0
    budget = limit
    for e, sl in shortlisted:
        eid = str(e.id)
        if eid in absorbed_by:
            continue
        if sl.needs_llm:
            if budget <= 0:
                logger.warning("  budget di %d giudizi LLM esaurito per questo cliente", limit)
                break
            budget -= 1
        match = er.decide(
            sl, name=e.canonical_name, entity_type=e.entity_type or "other", llm=llm
        )
        if match is None or match.entity_id not in born:
            continue
        target = _survivor(match.entity_id)
        if target == eid:  # il match risale a `e` stessa lungo la catena
            continue

        survivor, loser = (target, eid) if born[target] <= born[eid] else (eid, target)
        if apply:
            with canonical_session(consultant, client) as writer:
                merge_entities(writer, consultant, client, survivor, loser)
            print(f"  MERGE {name_of[loser]!r} -> {name_of[survivor]!r}")
        else:
            print(
                f"  [dry-run] MERGE {name_of[loser]!r} -> {name_of[survivor]!r}  "
                f"({match.reason[:80]})"
            )
        absorbed_by[loser] = survivor
        n_merges += 1

    return n_merges


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #


def _clients(consultant: str, only: str | None) -> list[str]:
    with canonical_session(consultant) as session:
        rows = session.execute(text("SELECT id FROM client ORDER BY created_at")).all()
    ids = [str(r.id) for r in rows]
    return [c for c in ids if not only or c == only]


def run(args: argparse.Namespace) -> Stats:
    stats = Stats()
    consultant = args.consultant or settings.default_consultant_id

    llm = None
    if not args.no_sweep:
        llm = er.build_llm()
        if llm is None:
            print("OPENAI_API_KEY assente: sweep disattivato (solo backfill).", file=sys.stderr)

    clients = _clients(consultant, args.client)
    if not clients:
        print("nessun cliente da processare")
        return stats

    for client in clients:
        print(f"cliente {client}")
        if not args.no_backfill:
            stats.backfilled += backfill_client(consultant, client, args.apply)
        if llm is not None:
            stats.merges += sweep_client(
                consultant, client, llm, args.apply, args.limit
            )
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--consultant", help="consultant_id (default: settings)")
    parser.add_argument("--client", help="limita a un client_id")
    parser.add_argument("--apply", action="store_true", help="esegue (default: dry-run)")
    parser.add_argument("--no-backfill", action="store_true")
    parser.add_argument("--no-sweep", action="store_true")
    parser.add_argument(
        "--limit", type=int, default=200, help="max giudizi LLM per cliente (default 200)"
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if not settings.canonical_database_url:
        print("CANONICAL_DATABASE_URL non configurata", file=sys.stderr)
        return 2

    stats = run(args)
    verb = "applicati" if args.apply else "(dry-run)"
    print(f"\n{verb}: backfill {stats.backfilled} embedding, {stats.merges} fusioni")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
