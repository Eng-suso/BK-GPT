"""Gateway unico di lettura del cervello (INV-9).

Nessun tool o agente interroga Neo4j / Postgres-KG / Mem0 direttamente: si
passa da qui, che inietta lo scope (`consultant_id`, `client_id`) in ogni
query. Con Neo4j Community senza subgraph ACL, e con Mem0 senza tenant ACL,
questo e' l'unico punto di enforcement in lettura.

`graph_retrieve` (grafo tipizzato, retrieval ibrido — P3):
  1. seed lessicale — nomi entita' + parole della query -> entity_id
     (Postgres kg_entity, RLS per client)
  2. seed vettoriale — embedding della query -> cosine su kg_chunk (RLS) ->
     source_id dei chunk -> entita' con quella provenance
  3. fusione RRF dei due ranking -> lista seed unica
  4. espansione — k-hop in Neo4j dai seed, ogni nodo del path filtrato per
     client_id
  5. idratazione — ogni id opaco -> testo autoritativo da Postgres (RLS):
     canonical_name, statement, title, ...
  I chunk piu' vicini tornano anche come contesto testuale (`chunks`).

`memory_search` (recall Mem0):
  - `user_id` Mem0 = mappa dal `consultant_id` (oggi mono-consulente locale)
  - post-filtro per `client_id` sui metadata: le memorie consultant-level
    (senza client_id) restano visibili ovunque, quelle client-scoped solo
    nel loro cliente

`workspace_read` (stato operativo):
  - snapshot scoped della workspace (Postgres, SoT operativa INV-8): project +
    processi + sources/decisions, filtrati per `process_ids`

Disattivato in silenzio se canonical / Neo4j / Mem0 non sono configurati: i
chiamanti degradano con uno status esplicito.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import text

from backend.db import canonical_session
from backend.memory import embeddings, mem0_client
from backend.memory.knowledge_graph import neo4j_store
from backend.memory.mem0_client import Mem0Disabled
from backend.settings import settings

logger = logging.getLogger(__name__)

_WORD = re.compile(r"[\wÀ-ÿ]{3,}")


def graph_available() -> bool:
    return bool(settings.canonical_database_url) and neo4j_store.is_enabled()


def memory_available() -> bool:
    return mem0_client.is_enabled()


def procedural_available() -> bool:
    return bool(settings.canonical_database_url)


def _resolve_seed_entities(
    consultant_id: str,
    client_id: str,
    entity_names: list[str],
    query: str,
) -> list[str]:
    terms = {" ".join(n.split()).casefold() for n in entity_names if n and n.strip()}
    terms |= {w.casefold() for w in _WORD.findall(query or "")}
    if not terms:
        return []
    exact = list(terms)
    like_patterns = [f"%{t}%" for t in terms]
    with canonical_session(consultant_id, client_id) as session:
        rows = session.execute(
            text(
                "SELECT id FROM kg_entity "
                "WHERE client_id = :cl AND status <> 'rejected' "
                "  AND (lower(canonical_name) = ANY(:exact) "
                "       OR aliases && CAST(:exact AS text[]) "  # P2: alias noti
                "       OR lower(canonical_name) LIKE ANY(:like)) "
                # match esatto (nome o alias) prima, poi nome piu' corto (piu'
                # probabilmente l'entita' precisa): da' un ranking vero alla RRF
                "ORDER BY (lower(canonical_name) = ANY(:exact) "
                "          OR aliases && CAST(:exact AS text[])) DESC, "
                "         char_length(canonical_name) "
                "LIMIT 40"
            ),
            {"cl": client_id, "exact": exact, "like": like_patterns},
        ).all()
    return [str(r.id) for r in rows]


def _vector_seed(
    consultant_id: str,
    client_id: str,
    query: str,
    chunk_k: int,
) -> tuple[list[str], list[dict]]:
    """Seed vettoriale: embedda la query, cerca i chunk piu' vicini (RLS per
    client), risale a `source_id` -> entita' con quella provenance.

    Ritorna `(entity_ids ordinati per rilevanza, chunk di contesto)`.
    """
    if not (query or "").strip() or not embeddings.available():
        return [], []
    with canonical_session(consultant_id, client_id) as session:
        has_chunks = session.execute(
            text(
                "SELECT 1 FROM kg_chunk "
                "WHERE client_id = :cl AND embedding IS NOT NULL LIMIT 1"
            ),
            {"cl": client_id},
        ).first()
        if not has_chunks:  # niente da cercare: risparmia la chiamata all'embedder
            return [], []

        vec = embeddings.embed_query(query)
        if vec is None:
            return [], []
        q = embeddings.to_pgvector(vec)
        chunk_rows = session.execute(
            text(
                "SELECT source_id, content, "
                "       1 - (embedding <=> CAST(:q AS vector)) AS score "
                "FROM kg_chunk "
                "WHERE client_id = :cl AND embedding IS NOT NULL "
                "ORDER BY embedding <=> CAST(:q AS vector) "
                "LIMIT :k"
            ),
            {"q": q, "cl": client_id, "k": chunk_k},
        ).all()
        if not chunk_rows:
            return [], []
        source_ids = list({str(r.source_id) for r in chunk_rows})
        ent_rows = session.execute(
            text(
                "SELECT DISTINCT id FROM kg_entity "
                "WHERE client_id = :cl AND status <> 'rejected' "
                "  AND source_ids && CAST(:sids AS uuid[])"
            ),
            {"cl": client_id, "sids": source_ids},
        ).all()
    chunks = [
        {"content": r.content, "score": round(float(r.score), 4)}
        for r in chunk_rows
    ]
    return [str(r.id) for r in ent_rows], chunks


def _rrf(ranked_lists: list[list[str]], k: int = 60) -> list[str]:
    """Reciprocal Rank Fusion: combina piu' ranking di id in uno solo."""
    scores: dict[str, float] = {}
    for lst in ranked_lists:
        for rank, item in enumerate(lst):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank + 1)
    return [item for item, _ in sorted(scores.items(), key=lambda kv: -kv[1])]


def _expand(
    client_id: str,
    seed_entity_ids: list[str],
    process_id: str | None,
    max_hops: int,
    limit: int,
) -> list[dict]:
    driver = neo4j_store.get_driver()
    hops = max(1, min(3, max_hops))
    cypher = (
        f"MATCH p = (seed)-[*1..{hops}]-(other) "
        "WHERE (seed.entity_id IN $eids OR seed.process_id = $pid) "
        "  AND all(n IN nodes(p) WHERE coalesce(n.client_id, $cid) = $cid) "
        "UNWIND relationships(p) AS r "
        "WITH DISTINCT r, startNode(r) AS a, endNode(r) AS b "
        "RETURN type(r) AS rt, properties(r) AS rp, "
        "       labels(a) AS la, properties(a) AS ap, "
        "       labels(b) AS lb, properties(b) AS bp "
        "LIMIT $lim"
    )
    with driver.session() as neo:
        result = neo.run(
            cypher,
            eids=seed_entity_ids,
            pid=str(process_id) if process_id else "",
            cid=str(client_id),
            lim=limit,
        )
        return [dict(record) for record in result]


_ID_PROP = {
    "Entity": "entity_id",
    "Process": "process_id",
    "Claim": "claim_id",
    "Gap": "gap_id",
    "Contradiction": "contradiction_id",
    "Impact": "impact_id",
}


def _node_ref(labels: list[str], props: dict) -> tuple[str, str] | None:
    for label in labels:
        prop = _ID_PROP.get(label)
        if prop and props.get(prop):
            return label, str(props[prop])
    return None


def _hydrate(consultant_id: str, client_id: str, triples: list[dict]) -> list[dict]:
    by_label: dict[str, set[str]] = {}
    for tri in triples:
        for labels, props in ((tri["la"], tri["ap"]), (tri["lb"], tri["bp"])):
            ref = _node_ref(labels, props)
            if ref:
                by_label.setdefault(ref[0], set()).add(ref[1])

    names: dict[tuple[str, str], str] = {}
    _q = {
        "Entity": "SELECT id, canonical_name AS label FROM kg_entity WHERE id = ANY(:ids)",
        "Process": "SELECT id, name AS label FROM process WHERE id = ANY(:ids)",
        "Claim": "SELECT id, statement AS label FROM kg_claim WHERE id = ANY(:ids)",
        "Gap": "SELECT id, title AS label FROM kg_gap WHERE id = ANY(:ids)",
        "Contradiction": "SELECT id, title AS label FROM kg_contradiction WHERE id = ANY(:ids)",
        "Impact": "SELECT id, title AS label FROM kg_impact WHERE id = ANY(:ids)",
    }
    with canonical_session(consultant_id, client_id) as session:
        for label, ids in by_label.items():
            if label not in _q:
                continue
            for row in session.execute(text(_q[label]), {"ids": list(ids)}).all():
                names[(label, str(row.id))] = row.label

    def _label_of(labels, props) -> str:
        ref = _node_ref(labels, props)
        if not ref:
            return "?"
        return names.get(ref, ref[1])  # nome autoritativo, o id se non idratato

    matches = []
    for tri in triples:
        matches.append(
            {
                "source": _label_of(tri["la"], tri["ap"]),
                "relation": tri["rt"],
                "target": _label_of(tri["lb"], tri["bp"]),
                "confidence": tri["rp"].get("confidence"),
                "confirmed": tri["rp"].get("confirmed"),
            }
        )
    return matches


def graph_retrieve(
    *,
    consultant_id: str,
    client_id: str,
    query: str = "",
    entity_names: list[str] | None = None,
    process_id: str | None = None,
    relation_focus: str | None = None,
    max_hops: int = 2,
    limit: int = 25,
) -> dict[str, Any]:
    if not graph_available():
        return {"status": "not_configured", "matches": [], "count": 0, "chunks": []}

    try:
        lexical = _resolve_seed_entities(consultant_id, client_id, entity_names or [], query)
        vector, chunks = _vector_seed(consultant_id, client_id, query, chunk_k=max(limit // 3, 8))
        seeds = _rrf([lexical, vector])[:40]
        if not seeds and not process_id:
            return {
                "status": "empty", "matches": [], "count": 0,
                "chunks": chunks, "reason": "nessun seed",
            }

        triples = _expand(client_id, seeds, process_id, max_hops, limit)
        matches = _hydrate(consultant_id, client_id, triples) if triples else []
    except Exception as exc:  # noqa: BLE001 — la lettura non deve mai far fallire il tool
        logger.warning("gateway.graph_retrieve fallito: %s", exc)
        return {"status": "error", "matches": [], "count": 0, "chunks": [], "reason": str(exc)}

    if relation_focus:
        focus = relation_focus.strip().upper().replace("-", "_")
        matches.sort(key=lambda m: 0 if focus in (m["relation"] or "") else 1)

    status = "ok" if (matches or chunks) else "empty"
    return {"status": status, "count": len(matches), "matches": matches, "chunks": chunks}


# --------------------------------------------------------------------------- #
# memory_search — recall Mem0 con scope iniettato (INV-9)
# --------------------------------------------------------------------------- #


def _mem0_user_id(consultant_id: str) -> str:
    """Mem0 non ha tenant ACL: lo scope consulente e' l'`user_id`.

    Setup mono-consulente locale -> un solo `user_id` (`settings.mem0_user_id`).
    La mappa `consultant_id -> user_id` vivra' qui quando ci saranno piu'
    consulenti."""
    return settings.mem0_user_id


def _mem0_items(raw: Any) -> list:
    if isinstance(raw, dict):
        return raw.get("results") or raw.get("memories") or []
    return raw or []


def memory_search(
    *,
    consultant_id: str,
    client_id: str | None = None,
    query: str,
    category: str | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """Recall dalla memoria Mem0 con lo scope iniettato (INV-9).

    Le memorie consultant-level (senza `client_id` nei metadata) restano
    visibili in ogni contesto; quelle client-scoped solo nel loro cliente.
    Ritorna `{"status": ok|empty|not_configured|error, "count", "matches"}`.
    """
    memory = mem0_client.get_memory()
    if isinstance(memory, Mem0Disabled):
        return {"status": "not_configured", "matches": [], "count": 0, "reason": memory.reason}

    search_query = f"[{category}] {query}" if category else (query or "")
    try:
        raw = memory.search(
            query=search_query,
            filters={"user_id": _mem0_user_id(consultant_id)},
            limit=max(limit * 4, 20),
        )
    except Exception as exc:  # noqa: BLE001 — la lettura non deve far fallire il tool
        logger.warning("gateway.memory_search fallito: %s", exc)
        return {"status": "error", "matches": [], "count": 0, "reason": str(exc)}

    cid = str(client_id) if client_id else None
    matches: list[dict[str, Any]] = []
    for item in _mem0_items(raw):
        if not isinstance(item, dict):
            matches.append(
                {"memory_id": None, "memory": str(item), "score": None, "client_scoped": False}
            )
        else:
            mem_client = (item.get("metadata") or {}).get("client_id")
            if mem_client and mem_client != cid:
                continue  # memoria di un altro cliente: fuori scope
            matches.append(
                {
                    "memory_id": item.get("id") or item.get("memory_id") or item.get("uuid"),
                    "memory": item.get("memory")
                    or item.get("text")
                    or item.get("content")
                    or str(item),
                    "score": item.get("score"),
                    "client_scoped": bool(mem_client),
                }
            )
        if len(matches) >= limit:
            break

    return {"status": "ok" if matches else "empty", "count": len(matches), "matches": matches}


# --------------------------------------------------------------------------- #
# procedural_retrieve — playbook appresi 'active', scoped (INV-9 / INV-12)
# --------------------------------------------------------------------------- #

_PROCEDURAL_KINDS = ("playbook", "heuristic", "checklist")


def _rank_playbooks(rows: list, task_text: str) -> list:
    """Ranking lessicale: sovrapposizione di parole tra `task_text` e
    `title` + `applies_when`. A parita' preferisce il playbook client-scoped
    (piu' specifico) e poi la confidence."""
    terms = {w.lower() for w in _WORD.findall(task_text or "")}
    scored = []
    for row in rows:
        haystack = f"{row.title or ''} {row.applies_when or ''}".lower()
        overlap = len(terms & {w.lower() for w in _WORD.findall(haystack)})
        scored.append((overlap, 1 if row.client_id else 0, float(row.confidence or 0.0), row))
    scored.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    return [item[3] for item in scored]


def procedural_retrieve(
    *,
    consultant_id: str,
    client_id: str | None = None,
    task_text: str = "",
    kinds: list[str] | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """Playbook appresi `active` pertinenti al task, con lo scope iniettato.

    RLS fa il grosso: aperto `canonical_session(consultant_id, client_id)`, i
    playbook consultant-scoped (`client_id IS NULL`) sono sempre visibili,
    quelli client-scoped solo nel loro cliente. Aperto senza `client_id` si
    vedono solo i consultant-scoped.

    Ritorna `{"status": ok|empty|not_configured|error, "count", "playbooks"}`.
    """
    if not procedural_available():
        return {"status": "not_configured", "playbooks": [], "count": 0}

    wanted = [k for k in (kinds or _PROCEDURAL_KINDS) if k in _PROCEDURAL_KINDS]
    if not wanted:
        wanted = list(_PROCEDURAL_KINDS)

    try:
        with canonical_session(consultant_id, client_id) as session:
            rows = session.execute(
                text(
                    "SELECT id, scope, kind, title, applies_when, body, confidence, client_id "
                    "FROM procedural_memory "
                    "WHERE status = 'active' AND kind = ANY(:kinds) "
                    "ORDER BY confidence DESC, updated_at DESC LIMIT 60"
                ),
                {"kinds": wanted},
            ).all()
    except Exception as exc:  # noqa: BLE001 — la lettura non deve far fallire il tool
        logger.warning("gateway.procedural_retrieve fallito: %s", exc)
        return {"status": "error", "playbooks": [], "count": 0, "reason": str(exc)}

    ranked = _rank_playbooks(rows, task_text)[: max(1, limit)]
    playbooks = [
        {
            "id": str(row.id),
            "scope": row.scope,
            "kind": row.kind,
            "title": row.title,
            "applies_when": row.applies_when,
            "body": row.body,
            "confidence": float(row.confidence or 0.0),
            "client_scoped": bool(row.client_id),
        }
        for row in ranked
    ]
    return {
        "status": "ok" if playbooks else "empty",
        "count": len(playbooks),
        "playbooks": playbooks,
    }


# --------------------------------------------------------------------------- #
# workspace_read — snapshot operativo della workspace, scoped (INV-9)
# --------------------------------------------------------------------------- #

_WS_SECTIONS = ("processes", "sources", "decisions")


def workspace_read(
    *,
    project_id: str,
    process_ids: list[str] | None = None,
    include: tuple[str, ...] = _WS_SECTIONS,
) -> dict[str, Any]:
    """Snapshot operativo scoped della workspace (Postgres, SoT operativa INV-8).

    Unico read che i tool di retrieval usano per il grounding operativo.
    `process_ids` filtra i processi + le sources/decisions collegate; quelle
    project-level (senza `process_id`) restano sempre. Project inesistente ->
    status `not_found`, nessuna eccezione.
    """
    from backend import workspace_database

    project = workspace_database.get_project(project_id)
    if project is None:
        return {"status": "not_found", "project": None}

    wanted = {str(p) for p in (process_ids or []) if p}
    out: dict[str, Any] = {"status": "ok", "project": project}

    if "processes" in include:
        procs = workspace_database.list_project_processes(project_id)
        out["processes"] = [p for p in procs if p.get("id") in wanted] if wanted else procs

    def _scoped(rows: list[dict]) -> list[dict]:
        if not wanted:
            return rows
        return [r for r in rows if not r.get("process_id") or r.get("process_id") in wanted]

    if "sources" in include:
        out["sources"] = _scoped(workspace_database.list_project_sources(project_id))
    if "decisions" in include:
        out["decisions"] = _scoped(workspace_database.list_project_decisions(project_id))

    return out
