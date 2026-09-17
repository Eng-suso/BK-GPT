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

`validate_payload` e' la stessa regola letta dal lato dell'accodamento: un
payload che il projector non saprebbe applicare non deve entrare in coda, dove
non c'e' piu' nessuno a cui dire che era sbagliato. Chi emette la chiama prima
dell'INSERT (canonical.py, scripts/kg_resolve_entities.py); il DB la ripete come
CHECK (migration 0017); il worker la usa per riconoscere un veleno e metterlo in
dead-letter senza consumare cinque tentativi su un errore che non passera' mai.
"""

from __future__ import annotations

import re

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

PAYLOAD_KINDS = ("node", "edge", "node_delete", "edge_delete")


class InvalidGraphPayload(ValueError):
    """Il payload non e' applicabile a Neo4j, e non lo sara' mai."""


def _ident(value: str, what: str) -> str:
    if not isinstance(value, str) or not _IDENT.match(value):
        raise InvalidGraphPayload(f"{what} non sicura per Cypher: {value!r}")
    return value


def _endpoint(payload: dict, key: str) -> None:
    node = payload.get(key)
    if not isinstance(node, dict):
        raise InvalidGraphPayload(f"payload graph_outbox: {key} mancante o non oggetto")
    _ident(node.get("label"), f"{key}.label")
    _ident(node.get("id_prop"), f"{key}.id_prop")
    if not str(node.get("id_value") or "").strip():
        raise InvalidGraphPayload(f"payload graph_outbox: {key}.id_value vuoto")


def validate_payload(payload: object) -> dict:
    """Verifica che il payload sia una delle quattro forme applicabili.

    Args:
        payload: Il payload da accodare o appena letto dalla coda, non affidabile.

    Returns:
        Lo stesso payload, quando e' valido.

    Raises:
        InvalidGraphPayload: Se manca `kind`, se il `kind` non e' fra
            `PAYLOAD_KINDS`, o se la forma di quel `kind` e' incompleta o non
            sicura per Cypher.
    """
    if not isinstance(payload, dict):
        raise InvalidGraphPayload(
            f"payload graph_outbox non e' un oggetto: {type(payload).__name__}"
        )
    kind = payload.get("kind")
    if kind not in PAYLOAD_KINDS:
        raise InvalidGraphPayload(f"payload graph_outbox non riconosciuto: kind={kind!r}")

    _ident(payload.get("label"), "label")
    if kind in ("node", "node_delete"):
        _ident(payload.get("id_prop"), "id_prop")
        if not str(payload.get("id_value") or "").strip():
            raise InvalidGraphPayload("payload graph_outbox: id_value vuoto")
    else:
        _endpoint(payload, "source")
        _endpoint(payload, "target")
    return payload


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
    kind = validate_payload(payload)["kind"]
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
    else:  # edge_delete — `validate_payload` ha gia' escluso tutto il resto
        session.execute_write(
            _delete_edge, payload["label"], payload["source"], payload["target"]
        )
