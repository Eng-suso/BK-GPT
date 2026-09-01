"""Applica i payload di graph_outbox a Neo4j (INV-7).

Il payload e' gia' materializzato e B+-safe dal writer canonical (canonical.py):
il projector NON rilegge Postgres, NON conosce catalog.py, non decide nulla.
Solo MERGE / DETACH DELETE idempotenti.

Forme di payload:
  node          {kind, label, id_prop, id_value, props}
  edge          {kind, label, source:{label,id_prop,id_value},
                              target:{label,id_prop,id_value}, props}
  node_delete   {kind, label, id_prop, id_value}
  edge_delete   {kind, label, source:{...}, target:{...}}
"""

from __future__ import annotations

import re

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _ident(value: str, what: str) -> str:
    if not isinstance(value, str) or not _IDENT.match(value):
        raise ValueError(f"{what} non sicura per Cypher: {value!r}")
    return value


def _merge_node(tx, label, id_prop, id_value, props):
    tx.run(
        f"MERGE (n:{_ident(label, 'label')} {{{_ident(id_prop, 'id_prop')}: $id}}) "
        f"SET n += $props",
        id=id_value,
        props=props or {},
    )


def _delete_node(tx, label, id_prop, id_value):
    tx.run(
        f"MATCH (n:{_ident(label, 'label')} {{{_ident(id_prop, 'id_prop')}: $id}}) "
        f"DETACH DELETE n",
        id=id_value,
    )


def _merge_edge(tx, label, source, target, props):
    # MERGE anche sugli endpoint: l'arco atterra a prescindere dall'ordine di
    # arrivo dei payload; il nodo vero riempira' le props col suo payload.
    tx.run(
        f"MERGE (a:{_ident(source['label'], 'label')} "
        f"{{{_ident(source['id_prop'], 'id_prop')}: $sid}}) "
        f"MERGE (b:{_ident(target['label'], 'label')} "
        f"{{{_ident(target['id_prop'], 'id_prop')}: $tid}}) "
        f"MERGE (a)-[r:{_ident(label, 'label')}]->(b) SET r += $props",
        sid=source["id_value"],
        tid=target["id_value"],
        props=props or {},
    )


def _delete_edge(tx, label, source, target):
    tx.run(
        f"MATCH (a:{_ident(source['label'], 'label')} "
        f"{{{_ident(source['id_prop'], 'id_prop')}: $sid}})"
        f"-[r:{_ident(label, 'label')}]->"
        f"(b:{_ident(target['label'], 'label')} "
        f"{{{_ident(target['id_prop'], 'id_prop')}: $tid}}) "
        f"DELETE r",
        sid=source["id_value"],
        tid=target["id_value"],
    )


def apply(session, payload: dict) -> None:
    kind = payload.get("kind")
    if kind == "node":
        session.execute_write(
            _merge_node,
            payload["label"],
            payload["id_prop"],
            payload["id_value"],
            payload.get("props"),
        )
    elif kind == "node_delete":
        session.execute_write(
            _delete_node, payload["label"], payload["id_prop"], payload["id_value"]
        )
    elif kind == "edge":
        session.execute_write(
            _merge_edge,
            payload["label"],
            payload["source"],
            payload["target"],
            payload.get("props"),
        )
    elif kind == "edge_delete":
        session.execute_write(
            _delete_edge, payload["label"], payload["source"], payload["target"]
        )
    else:
        raise ValueError(f"payload graph_outbox non riconosciuto: kind={kind!r}")
