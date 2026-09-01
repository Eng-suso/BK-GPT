"""Scrittura canonical della struttura KG + emit dell'outbox (INV-1 / INV-7).

Ogni `write_*`:
  1. INSERT nella tabella Postgres (kg_entity / kg_relation / ...);
  2. INSERT in graph_outbox il payload gia' B+-safe per Neo4j — nella STESSA
     transazione (canonical_session -> ruolo delir_app -> RLS + INSERT-only
     sull'outbox).

Il projector (projector.py) applichera' quei payload a Neo4j senza rileggere
Postgres. La mappa dei nodi/archi e delle whitelist e' catalog.py.

Questo modulo e' la porta di scrittura che l'ingestion (toolsets/*_memory.py)
usera' al posto del vecchio knowledge_graph_store.
"""

from __future__ import annotations

import secrets
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.db import canonical_session
from backend.memory.knowledge_graph import catalog

_ENTITY = catalog.NODE_BY_TABLE["kg_entity"]


def _nonce() -> str:
    return secrets.token_hex(8)


def _emit(
    session: Session,
    *,
    aggregate_type: str,
    aggregate_id: str,
    consultant_id: str,
    client_id: str | None,
    payload: dict[str, Any],
    op: str = "upsert",
) -> None:
    session.execute(
        text(
            "INSERT INTO graph_outbox "
            "(aggregate_type, aggregate_id, consultant_id, client_id, op, payload, dedupe_key) "
            "VALUES (:at, :aid, :cid, :clid, :op, CAST(:payload AS jsonb), :dk)"
        ),
        {
            "at": aggregate_type,
            "aid": aggregate_id,
            "cid": str(consultant_id),
            "clid": str(client_id) if client_id else None,
            "op": op,
            "payload": _json(payload),
            "dk": f"{aggregate_type}:{aggregate_id}:{_nonce()}",
        },
    )


def _json(value: dict) -> str:
    import json

    return json.dumps(value, default=str)


def _scope_props(row: dict) -> dict:
    return {
        "client_id": str(row["client_id"]) if row.get("client_id") else None,
        "project_id": str(row["project_id"]) if row.get("project_id") else None,
        "layer": row.get("layer", "L1"),
        "status": row.get("status", "active"),
        "confidence": row.get("confidence", 0.5),
    }


# --- Process (nodo di ancoraggio) -----------------------------------------

def write_process_node(
    consultant_id: str,
    client_id: str,
    process_id: str,
    name: str,
    *,
    project_id: str | None = None,
) -> None:
    """Proietta un nodo Process (ancoraggio per claim/gap/impact)."""
    props = {
        "process_id": str(process_id),
        "client_id": str(client_id),
        "project_id": str(project_id) if project_id else None,
        "layer": "L1",
        "status": "active",
        "confidence": 1.0,
        "name": name,
    }
    catalog.assert_projectable(props, context="Process")
    with canonical_session(consultant_id, client_id) as session:
        _emit(
            session,
            aggregate_type="process",
            aggregate_id=str(process_id),
            consultant_id=consultant_id,
            client_id=client_id,
            payload={
                "kind": "node",
                "label": "Process",
                "id_prop": "process_id",
                "id_value": str(process_id),
                "props": props,
            },
        )


# --- Entity --------------------------------------------------------------

def write_entity(
    consultant_id: str,
    client_id: str,
    entity_type: str,
    canonical_name: str,
    *,
    project_id: str | None = None,
    process_id: str | None = None,
    attributes: dict[str, Any] | None = None,
    source_ids: list[str] | None = None,
    confidence: float = 0.5,
) -> str:
    attributes = attributes or {}
    with canonical_session(consultant_id, client_id) as session:
        row = session.execute(
            text(
                "INSERT INTO kg_entity "
                "(consultant_id, client_id, project_id, process_id, scope, "
                " entity_type, canonical_name, attributes, source_ids, confidence, created_by) "
                "VALUES (:c, :cl, :p, :pr, 'client', :et, :name, CAST(:attrs AS jsonb), "
                "        CAST(:src AS uuid[]), :conf, 'agent') "
                "RETURNING id"
            ),
            {
                "c": str(consultant_id),
                "cl": str(client_id),
                "p": str(project_id) if project_id else None,
                "pr": str(process_id) if process_id else None,
                "et": entity_type,
                "name": canonical_name,
                "attrs": _json(attributes),
                "src": _pg_uuid_array(source_ids),
                "conf": confidence,
            },
        ).one()
        entity_id = str(row.id)

        whitelisted = {
            key: attributes[key]
            for key in _ENTITY.attr_whitelist
            if key in attributes
        }
        props = {
            "entity_id": entity_id,
            "client_id": str(client_id),
            "project_id": str(project_id) if project_id else None,
            "layer": "L1",
            "status": "active",
            "confidence": confidence,
            "entity_type": entity_type,
            **whitelisted,
        }
        catalog.assert_projectable(props, context=f"Entity {entity_type}")
        _emit(
            session,
            aggregate_type="entity",
            aggregate_id=entity_id,
            consultant_id=consultant_id,
            client_id=client_id,
            payload={
                "kind": "node",
                "label": "Entity",
                "id_prop": "entity_id",
                "id_value": entity_id,
                "props": props,
            },
        )
        return entity_id


# --- Relation ----------------------------------------------------------

def write_relation(
    consultant_id: str,
    client_id: str,
    source_entity_id: str,
    relation: str,
    target_entity_id: str,
    *,
    project_id: str | None = None,
    process_id: str | None = None,
    evidence: str = "",
    confidence: float = 0.5,
    confirmed: bool = False,
    source_ids: list[str] | None = None,
) -> str:
    label = _normalize_relation(relation)
    with canonical_session(consultant_id, client_id) as session:
        row = session.execute(
            text(
                "INSERT INTO kg_relation "
                "(consultant_id, client_id, project_id, process_id, scope, "
                " source_entity_id, target_entity_id, relation, evidence, confidence, "
                " confirmed, source_ids, created_by) "
                "VALUES (:c, :cl, :p, :pr, 'client', :s, :t, :rel, :ev, :conf, :cf, "
                "        CAST(:src AS uuid[]), 'agent') "
                "RETURNING id"
            ),
            {
                "c": str(consultant_id),
                "cl": str(client_id),
                "p": str(project_id) if project_id else None,
                "pr": str(process_id) if process_id else None,
                "s": str(source_entity_id),
                "t": str(target_entity_id),
                "rel": label,
                "ev": evidence,
                "conf": confidence,
                "cf": confirmed,
                "src": _pg_uuid_array(source_ids),
            },
        ).one()
        relation_id = str(row.id)
        props = {
            "relation_id": relation_id,
            "client_id": str(client_id),
            "project_id": str(project_id) if project_id else None,
            "layer": "L1",
            "status": "active",
            "confidence": confidence,
            "confirmed": confirmed,
        }
        catalog.assert_projectable(props, context=f"Relation {label}")
        _emit(
            session,
            aggregate_type="relation",
            aggregate_id=relation_id,
            consultant_id=consultant_id,
            client_id=client_id,
            payload={
                "kind": "edge",
                "label": label,
                "source": {
                    "label": "Entity",
                    "id_prop": "entity_id",
                    "id_value": str(source_entity_id),
                },
                "target": {
                    "label": "Entity",
                    "id_prop": "entity_id",
                    "id_value": str(target_entity_id),
                },
                "props": props,
            },
        )
        return relation_id


# --- helpers ---------------------------------------------------------------

def _pg_uuid_array(ids: list[str] | None) -> list[str]:
    return [str(i) for i in (ids or [])]


def _normalize_relation(relation: str) -> str:
    cleaned = "_".join(str(relation or "").strip().upper().split())
    cleaned = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in cleaned)
    cleaned = cleaned.strip("_")
    if not cleaned or not (cleaned[0].isalpha() or cleaned[0] == "_"):
        raise ValueError(f"label di relazione non valida: {relation!r}")
    return cleaned
