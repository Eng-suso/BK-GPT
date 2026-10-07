"""`graph_retrieve`: espansione nel grafo e idratazione da Postgres.

Passi 4-6 (vedi il pacchetto): espansione k-hop in Neo4j, o su Postgres quando
la proiezione non e' verificata fresca; idratazione con lo scope riapplicato;
l'esito dichiara da dove viene la risposta.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from backend.db import canonical_session
from backend.memory.knowledge_graph import neo4j_store
from backend.memory.projection_health import projection_report
from backend.services import degradation_counters
from backend.settings import settings
from backend.memory.gateway.scope import ReadScope, _authorized_source_ids, graph_available
from backend.memory.gateway.text_search import _context_chunks, _resolve_seed_entities, _rrf, _text_search

# La lunghezza di un path variabile non si passa come parametro in Cypher: si
# sceglie fra letterali fissi, cosi' nel testo della query non entra mai un
# valore calcolato.
_HOPS_PATTERN = {1: "*1..1", 2: "*1..2", 3: "*1..3"}


def _expand(
    client_id: str,
    seed_entity_ids: list[str],
    process_id: str | None,
    max_hops: int,
    limit: int,
    allowed_node_ids: list[str] | None,
) -> tuple[list[dict], bool]:
    """Espansione k-hop dai seed, con il budget speso dove serve (GR-02/GR-03).

    - `allowed_node_ids`: in una lettura scoped, i soli nodi leggibili (calcolati
      in Postgres da `_in_scope_node_ids`). Un path che passa da un nodo fuori
      scope non si enumera: prima l'espansione era client-wide e il `limit` si
      consumava su triple che l'idratazione avrebbe buttato. L'idratazione resta
      comunque il confine: questo e' budget, non sicurezza.
    - budget per seed: ogni seed ha al massimo `per_seed` path, e le triple
      escono a turni (il primo path di ogni seed, poi il secondo...), quindi un
      seed con cinquanta vicini non affama quello con tre.
    - degree cap: un hub non si attraversa come nodo intermedio. Il `LIMIT`
      della query limita le righe, non il lavoro: senza cap un hub moltiplica i
      path da enumerare.

    Ritorna le triple e se il budget ha tagliato qualcosa.
    """
    driver = neo4j_store.get_driver()
    hops = _HOPS_PATTERN[max(1, min(3, max_hops))]
    seeds = list(dict.fromkeys(seed_entity_ids))
    n_seeds = len(seeds) + (1 if process_id else 0)
    # Il doppio della quota giusta: un seed con pochi vicini lascia budget che
    # gli altri possono usare. L'equita' la tengono i turni, non il tetto.
    per_seed = max(3, -(-2 * limit // max(n_seeds, 1)))
    node_key = "coalesce(" + ", ".join(f"n.{p}" for p in _ID_PROP.values()) + ")"
    # Fail closed sul tenant: Neo4j Community non ha subgraph ACL, quindi
    # `n.client_id = $cid` E' il confine cliente. Un nodo senza `client_id`
    # (legacy, o una scrittura fuori dal projector) NON deve entrare nel path —
    # niente coalesce. Il write path (canonical.write_*) stampa sempre client_id;
    # assert_projectable lo impone. Vedi anche neo4j_store.purge_client (INV-10).
    cypher = (
        "CALL () { "
        "  UNWIND range(0, size($eids) - 1) AS rank "
        "  MATCH (seed:Entity {entity_id: $eids[rank]}) "
        "  RETURN seed, rank "
        "  UNION "
        "  MATCH (seed:Process {process_id: $pid}) "
        "  RETURN seed, size($eids) AS rank "
        "} "
        "WITH seed, rank WHERE seed.client_id = $cid "
        "CALL (seed) { "
        f"  MATCH p = (seed)-[{hops}]-(other) "
        "  WHERE all(n IN nodes(p) WHERE n.client_id = $cid "
        f"          AND ($allowed IS NULL OR {node_key} IN $allowed)) "
        "    AND all(n IN nodes(p)[1..-1] WHERE COUNT { (n)--() } <= $degree_cap) "
        "  RETURN p LIMIT $per_seed "
        "} "
        "WITH rank, collect(p) AS paths "
        "UNWIND range(0, size(paths) - 1) AS turn "
        "UNWIND relationships(paths[turn]) AS r "
        "WITH r, min(turn) AS turn, min(rank) AS rank "
        "ORDER BY turn, rank "
        "LIMIT $lim "
        "WITH r, startNode(r) AS a, endNode(r) AS b "
        "RETURN type(r) AS rt, properties(r) AS rp, "
        "       labels(a) AS la, properties(a) AS ap, "
        "       labels(b) AS lb, properties(b) AS bp"
    )
    with driver.session() as neo:
        result = neo.run(
            cypher,
            eids=seeds,
            pid=str(process_id) if process_id else "",
            cid=str(client_id),
            allowed=allowed_node_ids,
            degree_cap=int(settings.graph_expand_degree_cap),
            per_seed=per_seed,
            lim=limit + 1,
        )
        rows = [dict(record) for record in result]
    return rows[:limit], len(rows) > limit


# L'espansione su Postgres quando la proiezione non e' verificata fresca. Copre
# le relazioni fra entita' (`kg_relation`, la verita'); gli archi strutturali
# verso claim, lacune e contraddizioni esistono solo nella proiezione, e qui non
# si inventano. Non direzionata, come il pattern Cypher: un arco si attraversa
# da entrambi gli estremi. `rels` evita di ripercorrere lo stesso arco.
_CANONICAL_EXPAND_SQL = """
WITH RECURSIVE walk(entity_id, depth, rel_id, rels) AS (
    SELECT seed, 0, NULL::uuid, ARRAY[]::uuid[]
    FROM unnest(CAST(:seeds AS uuid[])) AS seed
  UNION ALL
    SELECT CASE WHEN r.source_entity_id = w.entity_id
                THEN r.target_entity_id ELSE r.source_entity_id END,
           w.depth + 1, r.id, w.rels || r.id
    FROM walk w
    JOIN kg_relation r
      ON r.source_entity_id = w.entity_id OR r.target_entity_id = w.entity_id
    WHERE w.depth < :hops
      AND r.client_id = CAST(:cl AS uuid)
      AND r.status = 'active'
      AND NOT r.id = ANY(w.rels)
      AND (CAST(:allowed AS uuid[]) IS NULL
           OR (r.source_entity_id = ANY(CAST(:allowed AS uuid[]))
               AND r.target_entity_id = ANY(CAST(:allowed AS uuid[]))))
)
SELECT r.relation, r.confidence, r.confirmed,
       r.source_entity_id, r.target_entity_id, hop.depth
FROM (SELECT rel_id, min(depth) AS depth FROM walk
      WHERE rel_id IS NOT NULL GROUP BY rel_id) AS hop
JOIN kg_relation r ON r.id = hop.rel_id
ORDER BY hop.depth, r.confidence DESC, r.id
LIMIT :lim
"""

# Senza seed di entita' ma con un processo: le entita' che le sue relazioni
# toccano, come in Neo4j il nodo Process e' il seed dell'espansione.
_PROCESS_SEEDS_SQL = """
SELECT DISTINCT e FROM (
  SELECT source_entity_id AS e FROM kg_relation
   WHERE process_id = CAST(:pid AS uuid) AND client_id = CAST(:cl AS uuid) AND status = 'active'
  UNION
  SELECT target_entity_id FROM kg_relation
   WHERE process_id = CAST(:pid AS uuid) AND client_id = CAST(:cl AS uuid) AND status = 'active'
) AS seeds
LIMIT 40
"""


def _expand_canonical(
    consultant_id: str,
    client_id: str,
    seed_entity_ids: list[str],
    process_id: str | None,
    max_hops: int,
    limit: int,
    allowed_node_ids: list[str] | None,
) -> tuple[list[dict], bool]:
    """Come `_expand`, ma leggendo la verita' invece della proiezione.

    Restituisce triple nella stessa forma di Neo4j, cosi' l'idratazione - che
    resta il confine di scope - non cambia. Massimo due salti: e' un ripiego,
    e una CTE ricorsiva su un hub a tre salti costa piu' della risposta.
    """
    seeds = list(dict.fromkeys(seed_entity_ids))
    with canonical_session(consultant_id, client_id) as session:
        if not seeds and process_id:
            seeds = [
                str(row.e)
                for row in session.execute(
                    text(_PROCESS_SEEDS_SQL), {"pid": str(process_id), "cl": str(client_id)}
                ).all()
            ]
        if not seeds:
            return [], False
        rows = session.execute(
            text(_CANONICAL_EXPAND_SQL),
            {
                "seeds": seeds,
                "hops": max(1, min(2, max_hops)),
                "cl": str(client_id),
                "allowed": allowed_node_ids,
                "lim": limit + 1,
            },
        ).all()
    triples = [
        {
            "rt": row.relation,
            "rp": {"confidence": row.confidence, "confirmed": row.confirmed},
            "la": ["Entity"],
            "ap": {"entity_id": str(row.source_entity_id)},
            "lb": ["Entity"],
            "bp": {"entity_id": str(row.target_entity_id)},
        }
        for row in rows
    ]
    return triples[:limit], len(triples) > limit


def _expand_canonical_for(consultant_id: str):
    """`_expand_canonical` con la firma di `_expand`, per sceglierle allo stesso modo."""

    def expand(client_id, seeds, process_id, max_hops, limit, allowed_node_ids):
        return _expand_canonical(
            consultant_id, client_id, seeds, process_id, max_hops, limit, allowed_node_ids
        )

    return expand


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


# Ogni nodo del grafo tipizzato porta la propria appartenenza in Postgres. Il
# `process` non ha un `process_id`: e' se stesso, quindi lo si confronta con
# l'id della riga.
_NODE_SELECT = {
    "Entity": (
        "SELECT id, canonical_name AS label, project_id, process_id, source_ids, "
        "       '' AS attributed_to, '' AS source_name "
        "FROM kg_entity"
    ),
    "Process": (
        "SELECT id, name AS label, project_id, id AS process_id, "
        "       CAST(ARRAY[] AS uuid[]) AS source_ids, "
        "       '' AS attributed_to, '' AS source_name "
        "FROM process"
    ),
    # Un claim non e' una stringa: chi lo dice e da quale fonte viaggiano con
    # lui, altrimenti a valle l'attribuzione si ricostruisce dal testo — ed e'
    # cosi' che nel V3 un'affermazione di uno e' finita in bocca a un altro.
    "Claim": (
        "SELECT id, statement AS label, project_id, process_id, source_ids, "
        "       attributed_to, source_name "
        "FROM kg_claim"
    ),
    "Gap": (
        "SELECT id, title AS label, project_id, process_id, source_ids, "
        "       '' AS attributed_to, '' AS source_name "
        "FROM kg_gap"
    ),
    "Contradiction": (
        "SELECT id, title AS label, project_id, process_id, source_ids, "
        "       '' AS attributed_to, '' AS source_name "
        "FROM kg_contradiction"
    ),
    "Impact": (
        "SELECT id, title AS label, project_id, process_id, source_ids, "
        "       '' AS attributed_to, '' AS source_name "
        "FROM kg_impact"
    ),
}

_HYDRATE_SQL = {label: sql + " WHERE id = ANY(:ids)" for label, sql in _NODE_SELECT.items()}

# Candidati per `_in_scope_node_ids`: un sovrainsieme largo di cio' che puo'
# essere in scope. A decidere e' `_Node.in_scope`, la stessa regola
# dell'idratazione: la regola resta scritta in un posto solo.
_KG_CANDIDATES = (
    " WHERE client_id = CAST(:cl AS uuid)"
    "   AND (process_id = CAST(:pid AS uuid)"
    "        OR project_id = CAST(:prj AS uuid)"
    "        OR source_ids && CAST(:sids AS uuid[]))"
)
_SCOPE_CANDIDATES_SQL = {
    label: sql + _KG_CANDIDATES for label, sql in _NODE_SELECT.items() if label != "Process"
}
_SCOPE_CANDIDATES_SQL["Process"] = _NODE_SELECT["Process"] + (
    " WHERE client_id = CAST(:cl AS uuid)"
    "   AND (id = CAST(:pid AS uuid) OR project_id = CAST(:prj AS uuid))"
)


@dataclass(frozen=True)
class _Node:
    label: str
    project_id: str | None
    process_id: str | None
    source_ids: tuple[str, ...]
    attributed_to: str = ""
    source_name: str = ""

    @property
    def attribution(self) -> str | None:
        """Chi risponde di questo nodo, quando qualcuno ne risponde."""
        return (self.attributed_to or "").strip() or (self.source_name or "").strip() or None

    def in_scope(self, scope: ReadScope, authorized_sources: set[str]) -> bool:
        if not scope.narrowed:
            return True
        if self.process_id and scope.process_id:
            if str(self.process_id) == str(scope.process_id):
                return True
        elif not self.process_id and self.project_id and scope.project_id:
            if str(self.project_id) == str(scope.project_id):
                return True
        # Un nodo condiviso fra piu' processi (tipicamente un'entita' riusata)
        # resta leggibile solo se almeno una delle sue fonti e' autorizzata qui.
        return bool(authorized_sources and set(self.source_ids) & authorized_sources)


def _node_from_row(row: Any) -> _Node:
    return _Node(
        label=row.label,
        project_id=str(row.project_id) if row.project_id else None,
        process_id=str(row.process_id) if row.process_id else None,
        source_ids=tuple(str(s) for s in (row.source_ids or ())),
        attributed_to=str(getattr(row, "attributed_to", "") or ""),
        source_name=str(getattr(row, "source_name", "") or ""),
    )


def _in_scope_node_ids(
    consultant_id: str,
    scope: ReadScope,
    authorized_sources: list[str] | None,
) -> list[str] | None:
    """Gli id dei nodi che questa lettura puo' vedere, per potare l'espansione
    in Neo4j prima che consumi il budget (GR-03). `None` = nessun confine.

    Stessa regola di `_hydrate` (`_Node.in_scope`), quindi l'espansione potata
    non perde nessuna tripla che l'idratazione avrebbe tenuto. Non sostituisce
    l'idratazione: un nodo che cambia scope fra le due letture viene comunque
    scartato la'.
    """
    if not scope.narrowed:
        return None
    allowed_sources = set(authorized_sources or ())
    params = {
        "cl": scope.client_id,
        "pid": scope.process_id,
        "prj": scope.project_id,
        "sids": sorted(allowed_sources),
    }
    ids: list[str] = []
    with canonical_session(consultant_id, scope.client_id) as session:
        for sql in _SCOPE_CANDIDATES_SQL.values():
            for row in session.execute(text(sql), params).all():
                if _node_from_row(row).in_scope(scope, allowed_sources):
                    ids.append(str(row.id))
    return ids


def _hydrate(
    consultant_id: str,
    scope: ReadScope,
    triples: list[dict],
    authorized_sources: list[str] | None,
) -> list[dict]:
    """Da triple opache a triple leggibili, riapplicando il confine di lettura.

    Neo4j Community non ha subgraph ACL e conosce solo il cliente: e' Postgres
    a sapere a quale progetto e processo appartiene ogni nodo. Una tripla con
    anche un solo estremo fuori scope - o non idratabile - viene scartata:
    fail closed, perche' e' esattamente da li' che nel test E2E V2 sono entrati
    i fatti di un altro processo.
    """
    by_label: dict[str, set[str]] = {}
    for tri in triples:
        for labels, props in ((tri["la"], tri["ap"]), (tri["lb"], tri["bp"])):
            ref = _node_ref(labels, props)
            if ref:
                by_label.setdefault(ref[0], set()).add(ref[1])

    nodes: dict[tuple[str, str], _Node] = {}
    with canonical_session(consultant_id, scope.client_id) as session:
        for label, ids in by_label.items():
            if label not in _HYDRATE_SQL:
                continue
            for row in session.execute(text(_HYDRATE_SQL[label]), {"ids": list(ids)}).all():
                nodes[(label, str(row.id))] = _node_from_row(row)

    allowed = set(authorized_sources or ())

    def _node_of(labels, props) -> tuple[str, _Node | None]:
        ref = _node_ref(labels, props)
        if not ref:
            return "?", None
        node = nodes.get(ref)
        # Non idratato: in una lettura scoped non si tiene un id opaco di cui
        # non si sa la provenienza.
        return (node.label if node else ref[1]), node

    matches = []
    for tri in triples:
        source_label, source_node = _node_of(tri["la"], tri["ap"])
        target_label, target_node = _node_of(tri["lb"], tri["bp"])
        if scope.narrowed:
            if source_node is None or target_node is None:
                continue
            if not source_node.in_scope(scope, allowed):
                continue
            if not target_node.in_scope(scope, allowed):
                continue
        matches.append(
            {
                "source": source_label,
                "relation": tri["rt"],
                "target": target_label,
                "confidence": tri["rp"].get("confidence"),
                "confirmed": tri["rp"].get("confirmed"),
                # Chi risponde dei due estremi, quando sono affermazioni. Un
                # claim che arriva nel contesto senza la sua voce e' materiale
                # per una misattribuzione.
                "source_attribution": source_node.attribution if source_node else None,
                "target_attribution": target_node.attribution if target_node else None,
                "process_id": (
                    (source_node.process_id if source_node else None)
                    or (target_node.process_id if target_node else None)
                ),
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
    scope_project_id: str | None = None,
    scope_process_id: str | None = None,
    allow_client_wide: bool = False,
    relation_focus: str | None = None,
    max_hops: int = 2,
    limit: int = 25,
) -> dict[str, Any]:
    """Retrieval sul grafo dentro un confine di lettura dichiarato.

    `scope_project_id` / `scope_process_id` sono l'autorizzazione: l'evidenza
    leggibile e' quella del processo corrente piu' quella project-level. Non
    e' un suggerimento di ranking - le righe fuori scope non vengono proprio
    lette. `process_id` resta il seed di espansione in Neo4j, cosa diversa.

    Senza confine la chiamata e' rifiutata (`status="blocked"`), a meno che il
    chiamante dichiari `allow_client_wide=True`: c'e' un uso legittimo
    (cutover, sweep, letture consulente), ma dev'essere una scelta scritta.
    """
    if not graph_available():
        return {"status": "not_configured", "matches": [], "count": 0, "chunks": []}

    scope = ReadScope(
        client_id=str(client_id),
        project_id=scope_project_id,
        process_id=scope_process_id,
        client_wide=allow_client_wide,
    )
    if not scope.narrowed and not allow_client_wide:
        degradation_counters.bump("graph_retrieve", "unscoped_call")
        return {
            "status": "blocked",
            "matches": [], "count": 0, "chunks": [],
            "reason": (
                "retrieval senza scope: serve scope_project_id/scope_process_id, "
                "oppure allow_client_wide=True dichiarato dal chiamante"
            ),
        }

    try:
        with canonical_session(consultant_id, scope.client_id) as session:
            authorized_sources = _authorized_source_ids(session, scope)
        name_seeds = _resolve_seed_entities(
            consultant_id, scope, entity_names or [], query, authorized_sources
        )
        text_hit = _text_search(
            consultant_id, scope, query, k=max(limit // 3, 8), source_ids=authorized_sources
        )
        seeds = [
            eid
            for eid, _ in _rrf([name_seeds, list(text_hit.entity_ids)])
        ][:40]
        chunks = _context_chunks(query, text_hit)
        if not seeds and not process_id:
            return {
                "status": "empty", "matches": [], "count": 0,
                "chunks": chunks, "reason": "nessun seed",
            }

        allowed_nodes = _in_scope_node_ids(consultant_id, scope, authorized_sources)
        # Una proiezione non verificata fresca non si serve: ne' quella indietro
        # ne' quella di cui non si sa. Si legge la verita' su Postgres, con
        # meno archi ma nessuno falso.
        projection = projection_report(scope.client_id)
        expand = _expand if projection.readable else _expand_canonical_for(consultant_id)
        triples, truncated = expand(
            client_id, seeds, process_id, max_hops, limit, allowed_nodes
        )
        matches = (
            _hydrate(consultant_id, scope, triples, authorized_sources) if triples else []
        )
    except Exception as exc:  # noqa: BLE001 — la lettura non deve mai far fallire il tool
        degradation_counters.bump("graph_retrieve", "error", detail=str(exc))
        return {"status": "error", "matches": [], "count": 0, "chunks": [], "reason": str(exc)}

    if relation_focus:
        focus = relation_focus.strip().upper().replace("-", "_")
        matches.sort(key=lambda m: 0 if focus in (m["relation"] or "") else 1)

    status = "ok" if (matches or chunks) else "empty"
    # `truncated`: il grafo aveva altre triple oltre il `limit`. Senza, un
    # `count` basso non si distingue da un grafo che sa poco.
    out: dict[str, Any] = {
        "status": status,
        "count": len(matches),
        "matches": matches,
        "chunks": chunks,
        "truncated": truncated,
    }
    # Da dove viene la risposta, sempre: chi la legge (l'agente) sa se ha
    # davanti il grafo completo o il ripiego sulle sole relazioni fra entita'.
    out["projection"] = {
        "health": projection.health.value,
        "served_from": "neo4j" if projection.readable else "postgres",
    }
    if not projection.readable:
        degradation_counters.bump("graph_retrieve", f"projection_{projection.health.value}")
        out["projection"]["reason"] = projection.reason
        out["projection"]["coverage"] = (
            "solo relazioni fra entita': i collegamenti a claim, lacune e "
            "contraddizioni arrivano quando la proiezione torna allineata"
        )
    if projection.stats and not projection.readable:
        out["staleness"] = projection.stats
    return out
