"""Ricostruzione della proiezione Neo4j di un cliente da Postgres (GR-01, INV-2).

INV-2 dice che la proiezione e' ricostruibile. Fino a qui non lo era in
pratica: la retention cancella le righe gia' processate di `graph_outbox`, e
una riga finita nel dead-letter lascia un buco in Neo4j che niente richiude.
Questo modulo ricostruisce dalle tabelle di dominio, non dalla coda: Postgres
e' la fonte, e la coda e' solo il modo in cui le modifiche viaggiano.

    diff(consultant_id, client_id)   cosa manca, cosa avanza, cosa e' diverso
    apply(consultant_id, client_id)  lo ripara, e ritorna il diff prima e dopo

`apply` non svuota il grafo prima di ricostruirlo: toglie solo cio' che avanza
(nodi e archi che Postgres non conosce piu', copie duplicate dello stesso nodo)
e poi riapplica tutto con `projector.apply`, che e' MERGE idempotente. Niente
finestra in cui chi legge trova un grafo vuoto.

Le props sono quelle del write path (`canonical.write_*`): il catalogo dice
quali colonne passano, e due regole che il catalogo non esprime sono replicate
qui con il rimando al punto di `canonical` da cui vengono. Se il write path
cambia forma, `tests/evals/l0_deterministic/test_kg_reproject.py` lo vede: confronta un grafo scritto
dal write path con lo stesso grafo ricostruito da qui.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text

from backend.db import canonical_session
from backend.memory.knowledge_graph import catalog, neo4j_store, projector

NodeKey = tuple[str, str]                       # (label, id)
EdgeKey = tuple[str, NodeKey, NodeKey]          # (tipo, sorgente, destinazione)

_ID_PROP_BY_LABEL = {spec.label: spec.id_prop for spec in catalog.NODES}


@dataclass
class ExpectedGraph:
    nodes: dict[NodeKey, dict[str, Any]] = field(default_factory=dict)
    edges: dict[EdgeKey, dict[str, Any]] = field(default_factory=dict)


@dataclass
class GraphDiff:
    missing_nodes: list[NodeKey]
    extra_nodes: list[NodeKey]
    duplicate_nodes: list[NodeKey]
    drifted_nodes: list[NodeKey]
    missing_edges: list[EdgeKey]
    extra_edges: list[EdgeKey]
    duplicate_edges: list[EdgeKey]
    drifted_edges: list[EdgeKey]
    expected_nodes: int
    expected_edges: int
    # nodi/archi del cliente senza un id del catalogo: non si sanno riparare
    # (non c'e' una riga Postgres a cui ricondurli), ma non vanno taciuti
    unkeyed: int = 0

    @property
    def clean(self) -> bool:
        return not (
            self.missing_nodes or self.extra_nodes or self.duplicate_nodes
            or self.drifted_nodes or self.missing_edges or self.extra_edges
            or self.duplicate_edges or self.drifted_edges or self.unkeyed
        )

    def summary(self) -> dict[str, int]:
        return {
            "expected_nodes": self.expected_nodes,
            "expected_edges": self.expected_edges,
            "missing_nodes": len(self.missing_nodes),
            "extra_nodes": len(self.extra_nodes),
            "duplicate_nodes": len(self.duplicate_nodes),
            "drifted_nodes": len(self.drifted_nodes),
            "missing_edges": len(self.missing_edges),
            "extra_edges": len(self.extra_edges),
            "duplicate_edges": len(self.duplicate_edges),
            "drifted_edges": len(self.drifted_edges),
            "unkeyed": self.unkeyed,
        }

    def differences(self) -> str:
        """Le sole voci diverse da zero, in una riga: il motivo di un CORRUPT."""
        counts = self.summary()
        return ", ".join(
            f"{key}={value}"
            for key, value in sorted(counts.items())
            if value and key not in ("expected_nodes", "expected_edges")
        )


# --------------------------------------------------------------------------- #
# atteso: da Postgres
# --------------------------------------------------------------------------- #

def _uuid(value: Any) -> str | None:
    return str(value) if value else None


def _node_payload(label: str, node_id: str, props: dict[str, Any]) -> dict[str, Any]:
    catalog.assert_projectable(props, context=f"reproject {label}")
    return {
        "kind": "node",
        "label": label,
        "id_prop": _ID_PROP_BY_LABEL[label],
        "id_value": node_id,
        "props": props,
    }


def _edge_payload(
    label: str, source: NodeKey, target: NodeKey, props: dict[str, Any]
) -> tuple[EdgeKey, dict[str, Any]]:
    catalog.assert_projectable(props, context=f"reproject {label}")
    payload = {
        "kind": "edge",
        "label": label,
        "source": {
            "label": source[0], "id_prop": _ID_PROP_BY_LABEL[source[0]], "id_value": source[1],
        },
        "target": {
            "label": target[0], "id_prop": _ID_PROP_BY_LABEL[target[0]], "id_value": target[1],
        },
        "props": props,
    }
    return (label, source, target), payload


def expected_graph(consultant_id: str, client_id: str) -> ExpectedGraph:
    """La proiezione che il write path avrebbe prodotto per questo cliente."""
    graph = ExpectedGraph()
    cl = str(client_id)
    with canonical_session(consultant_id, cl) as session:
        # Process: la tabella non ha layer/status/confidence, il write path li
        # scrive fissi (`canonical.write_process_node`).
        for row in session.execute(
            text("SELECT id, project_id, name FROM process WHERE client_id = :cl"), {"cl": cl}
        ).all():
            pid = str(row.id)
            graph.nodes[("Process", pid)] = _node_payload("Process", pid, {
                "process_id": pid, "client_id": cl, "project_id": _uuid(row.project_id),
                "layer": "L1", "status": "active", "confidence": 1.0, "name": row.name,
            })

        for spec in catalog.NODES:
            if spec.table == "process":
                continue
            columns = ", ".join(("id", "project_id", "layer", "status", "confidence", *spec.props))
            if spec.attr_whitelist:
                columns += ", attributes"
            for row in session.execute(
                text(f"SELECT {columns} FROM {spec.table} WHERE client_id = :cl"), {"cl": cl}
            ).all():
                node_id = str(row.id)
                props: dict[str, Any] = {
                    spec.id_prop: node_id,
                    "client_id": cl,
                    "project_id": _uuid(row.project_id),
                    "layer": row.layer,
                    "status": row.status,
                    "confidence": float(row.confidence) if row.confidence is not None else None,
                }
                for column in spec.props:
                    props[column] = getattr(row, column)
                attributes = getattr(row, "attributes", None) or {}
                props.update({k: attributes[k] for k in spec.attr_whitelist if k in attributes})
                graph.nodes[(spec.label, node_id)] = _node_payload(spec.label, node_id, props)

        for row in session.execute(
            text(
                "SELECT id, project_id, layer, status, confidence, confirmed, relation, "
                "       source_entity_id, target_entity_id "
                "FROM kg_relation WHERE client_id = :cl"
            ),
            {"cl": cl},
        ).all():
            key, payload = _edge_payload(
                row.relation,
                ("Entity", str(row.source_entity_id)),
                ("Entity", str(row.target_entity_id)),
                {
                    "relation_id": str(row.id), "client_id": cl,
                    "project_id": _uuid(row.project_id), "layer": row.layer,
                    "status": row.status,
                    "confidence": float(row.confidence) if row.confidence is not None else None,
                    "confirmed": bool(row.confirmed),
                },
            )
            graph.edges[key] = payload

        for edge in catalog.STRUCTURAL_EDGES:
            from_label = catalog.NODE_BY_TABLE[edge.from_table].label
            for row in session.execute(
                text(f"SELECT id, process_id, {edge.via} AS via FROM {edge.from_table} "
                     "WHERE client_id = :cl"),
                {"cl": cl},
            ).all():
                if edge.array:
                    targets = [str(t) for t in (row.via or ())]
                    # `canonical.write_gap/contradiction/impact`: senza processi
                    # colpiti dichiarati, l'arco va al processo della riga.
                    if not targets and edge.via == "affected_process_ids" and row.process_id:
                        targets = [str(row.process_id)]
                else:
                    targets = [str(row.via)] if row.via else []
                this = (from_label, str(row.id))
                for target_id in targets:
                    other = (
                        edge.to_node if edge.from_node == from_label else edge.from_node,
                        target_id,
                    )
                    source, target = (this, other) if edge.from_node == from_label else (other, this)
                    key, payload = _edge_payload(edge.label, source, target, {"client_id": cl})
                    graph.edges[key] = payload
    return graph


# --------------------------------------------------------------------------- #
# presente: da Neo4j
# --------------------------------------------------------------------------- #

def _node_key(labels: list[str], props: dict[str, Any]) -> NodeKey | None:
    for label in labels:
        id_prop = _ID_PROP_BY_LABEL.get(label)
        if id_prop and props.get(id_prop):
            return label, str(props[id_prop])
    return None


def _actual_graph(client_id: str) -> tuple[
    dict[NodeKey, list[dict[str, Any]]], dict[EdgeKey, list[dict[str, Any]]], int
]:
    """Nodi ed archi di questo cliente in Neo4j. Un nodo senza id riconoscibile
    si conta a parte: non si sa ripararlo, ma non va taciuto."""
    driver = neo4j_store.get_driver()
    if driver is None:
        raise neo4j_store.Neo4jUnavailable("Neo4j non configurato: niente da confrontare")
    nodes: dict[NodeKey, list[dict[str, Any]]] = {}
    edges: dict[EdgeKey, list[dict[str, Any]]] = {}
    unkeyed = 0
    with driver.session() as neo:
        for record in neo.run(
            "MATCH (n {client_id: $cid}) RETURN labels(n) AS l, properties(n) AS p",
            cid=str(client_id),
        ):
            key = _node_key(record["l"], record["p"])
            if key is None:
                unkeyed += 1
                continue
            nodes.setdefault(key, []).append(record["p"])
        for record in neo.run(
            "MATCH (a)-[r {client_id: $cid}]->(b) "
            "RETURN type(r) AS t, properties(r) AS p, "
            "       labels(a) AS la, properties(a) AS pa, labels(b) AS lb, properties(b) AS pb",
            cid=str(client_id),
        ):
            source = _node_key(record["la"], record["pa"])
            target = _node_key(record["lb"], record["pb"])
            if source is None or target is None:
                unkeyed += 1
                continue
            edges.setdefault((record["t"], source, target), []).append(record["p"])
    return nodes, edges, unkeyed


def _same(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    for key, value in expected.items():
        got = actual.get(key)
        if isinstance(value, float) and isinstance(got, (int, float)):
            if not math.isclose(value, float(got), rel_tol=1e-6, abs_tol=1e-9):
                return False
        elif value != got:
            return False
    return True


def diff(consultant_id: str, client_id: str) -> GraphDiff:
    expected = expected_graph(consultant_id, client_id)
    actual_nodes, actual_edges, unkeyed = _actual_graph(client_id)

    missing_nodes = sorted(set(expected.nodes) - set(actual_nodes))
    extra_nodes = sorted(set(actual_nodes) - set(expected.nodes))
    duplicate_nodes = sorted(k for k, copies in actual_nodes.items() if len(copies) > 1)
    drifted_nodes = sorted(
        k for k in set(expected.nodes) & set(actual_nodes)
        if not all(_same(expected.nodes[k]["props"], p) for p in actual_nodes[k])
    )
    missing_edges = sorted(set(expected.edges) - set(actual_edges))
    extra_edges = sorted(set(actual_edges) - set(expected.edges))
    duplicate_edges = sorted(
        k for k in set(expected.edges) & set(actual_edges) if len(actual_edges[k]) > 1
    )
    drifted_edges = sorted(
        k for k in set(expected.edges) & set(actual_edges)
        if len(actual_edges[k]) == 1
        and not _same(expected.edges[k]["props"], actual_edges[k][0])
    )
    return GraphDiff(
        missing_nodes=missing_nodes,
        extra_nodes=extra_nodes,
        duplicate_nodes=duplicate_nodes,
        drifted_nodes=drifted_nodes,
        missing_edges=missing_edges,
        extra_edges=extra_edges,
        duplicate_edges=duplicate_edges,
        drifted_edges=drifted_edges,
        expected_nodes=len(expected.nodes),
        expected_edges=len(expected.edges),
        unkeyed=unkeyed,
    )


# --------------------------------------------------------------------------- #
# riparazione
# --------------------------------------------------------------------------- #

@dataclass
class ApplyReport:
    before: GraphDiff
    after: GraphDiff
    deleted_nodes: int
    deleted_edges: int
    applied_nodes: int
    applied_edges: int


def apply(consultant_id: str, client_id: str) -> ApplyReport:
    """Porta la proiezione del cliente a coincidere con Postgres.

    Ordine: via cio' che avanza (nodi e archi orfani, copie duplicate - che si
    tolgono tutte e poi si ricreano una volta), poi tutti i nodi attesi,
    poi tutti gli archi attesi. Riapplicare tutto e non solo il mancante corregge
    anche le props andate alla deriva: e' MERGE, quindi costa tempo, non
    correttezza.
    """
    neo4j_store.ensure_schema()
    before = diff(consultant_id, client_id)
    expected = expected_graph(consultant_id, client_id)
    driver = neo4j_store.get_driver()
    deleted_nodes = deleted_edges = 0
    with driver.session() as neo:
        for label, node_id in (*before.extra_nodes, *before.duplicate_nodes):
            projector.apply(neo, {
                "kind": "node_delete", "label": label,
                "id_prop": _ID_PROP_BY_LABEL[label], "id_value": node_id,
            })
            deleted_nodes += 1
        for label, source, target in (*before.extra_edges, *before.duplicate_edges):
            projector.apply(neo, {
                "kind": "edge_delete", "label": label,
                "source": {"label": source[0], "id_prop": _ID_PROP_BY_LABEL[source[0]],
                           "id_value": source[1]},
                "target": {"label": target[0], "id_prop": _ID_PROP_BY_LABEL[target[0]],
                           "id_value": target[1]},
            })
            deleted_edges += 1
        for payload in expected.nodes.values():
            projector.apply(neo, payload)
        for payload in expected.edges.values():
            projector.apply(neo, payload)
    return ApplyReport(
        before=before,
        after=diff(consultant_id, client_id),
        deleted_nodes=deleted_nodes,
        deleted_edges=deleted_edges,
        applied_nodes=len(expected.nodes),
        applied_edges=len(expected.edges),
    )
