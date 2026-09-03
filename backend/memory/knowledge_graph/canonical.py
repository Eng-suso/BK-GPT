"""Scrittura canonical della struttura KG + emit dell'outbox (INV-1 / INV-7).

Ogni `write_*`:
  1. INSERT nella tabella Postgres (kg_entity / kg_relation / ...);
  2. INSERT in graph_outbox il payload gia' B+-safe per Neo4j — nella STESSA
     transazione (canonical_session -> ruolo delir_app -> RLS + INSERT-only
     sull'outbox).

Il projector (projector.py) applichera' quei payload a Neo4j senza rileggere
Postgres. La mappa dei nodi/archi e delle whitelist e' catalog.py.

Questo modulo e' l'unica porta di scrittura del knowledge graph: l'ingestion
(toolsets/*_memory.py) ci arriva via ``mirror.mirror_evidence``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
from contextlib import contextmanager
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.db import canonical_session
from backend.memory import embeddings
from backend.memory.knowledge_graph import catalog
from backend.memory.knowledge_graph import entity_resolution

logger = logging.getLogger(__name__)

_ENTITY = catalog.NODE_BY_TABLE["kg_entity"]

# Enum accettati dai CHECK delle tabelle (migration 0003/0006). Un valore fuori
# lista viene coerciato al default con un warning: meglio un dato leggermente
# impreciso che un INSERT fallito (soprattutto per il mirror best-effort).
_PROCESS_AREAS = frozenset(
    {"scope", "actor", "activity", "decision", "handoff", "system", "data",
     "exception", "control", "timing", "other"}
)
_CLAIM_STATUS = frozenset(
    {"confirmed", "partial", "contradicted", "inferred", "unsupported"}
)
_SEVERITY = frozenset({"low", "medium", "high", "critical", "blocking"})
_IMPACT_AREAS = frozenset(
    {"cost", "revenue", "working_capital", "risk", "quality", "time",
     "compliance", "efficiency", "roi"}
)
_SOURCE_KINDS = frozenset(
    {"interview_transcript", "document", "chat_extract",
     "system_export", "note", "observation"}
)


def _enum(value: Any, allowed: frozenset[str], default: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in allowed:
        return normalized
    if value:
        logger.warning("valore enum %r non valido, uso %r", value, default)
    return default


@contextmanager
def _open(consultant_id: str, client_id: str | None, tx: Session | None):
    """Riusa la transazione passata (`tx`) oppure ne apre una nuova.

    `write_evidence` passa una sola sessione a tutti i write cosi' l'intero
    pacchetto di evidenza e' atomico. I write chiamati singolarmente (test,
    cutover parziale) aprono la propria transazione come prima.
    """
    if tx is not None:
        yield tx
    else:
        with canonical_session(consultant_id, client_id) as session:
            yield session


def _json(value: dict) -> str:
    return json.dumps(value, default=str, sort_keys=True)


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
    # dedupe_key: nonce per riga. delir_app ha solo INSERT su graph_outbox
    # (nessun SELECT), quindi niente ON CONFLICT. Un eventuale doppione e'
    # innocuo: il projector riapplica a Neo4j in modo idempotente (MERGE), e
    # l'upsert su kg_entity/kg_relation garantisce id stabili.
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
            "dk": f"{aggregate_type}:{aggregate_id}:{secrets.token_hex(8)}",
        },
    )


# --- Process (nodo di ancoraggio) -----------------------------------------

def write_process_node(
    consultant_id: str,
    client_id: str,
    process_id: str,
    name: str,
    *,
    project_id: str | None = None,
    tx: Session | None = None,
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
    with _open(consultant_id, client_id, tx) as session:
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

# P2: applicare un match (UPDATE) e' deterministico. La DECISIONE ("questo nome
# e' l'entita' X?") la prende entity_resolution.plan_resolution PRIMA e FUORI
# da questa transazione: qui non si fanno ne' letture di resolution ne'
# chiamate LLM sotto lock.
_MERGE_ENTITY = text(
    "UPDATE kg_entity SET "
    "  aliases = CASE WHEN :alias = ANY(kg_entity.aliases) "
    "                  OR :alias = lower(kg_entity.canonical_name) "
    "             THEN kg_entity.aliases "
    "             ELSE kg_entity.aliases || ARRAY[:alias] END, "
    "  attributes = kg_entity.attributes || CAST(:attrs AS jsonb), "
    "  confidence = GREATEST(kg_entity.confidence, :conf), "
    "  source_ids = COALESCE((SELECT array_agg(DISTINCT x) FROM unnest("
    "    kg_entity.source_ids || CAST(:src AS uuid[])) AS x), kg_entity.source_ids), "
    "  embedding = COALESCE(kg_entity.embedding, CAST(:emb AS vector)), "
    "  embed_model = COALESCE(kg_entity.embed_model, :em), "
    "  embed_dim = COALESCE(kg_entity.embed_dim, :ed), "
    "  embed_version = COALESCE(kg_entity.embed_version, :ev) "
    "WHERE id = CAST(:mid AS uuid) AND status = 'active' "
    "RETURNING id, entity_type, confidence"
)
_INSERT_ENTITY = text(
    "INSERT INTO kg_entity "
    "(consultant_id, client_id, project_id, process_id, scope, "
    " entity_type, canonical_name, attributes, source_ids, confidence, "
    " embedding, embed_model, embed_dim, embed_version, created_by) "
    "VALUES (:c, :cl, :p, :pr, 'client', :et, :name, CAST(:attrs AS jsonb), "
    "        CAST(:src AS uuid[]), :conf, CAST(:emb AS vector), :em, :ed, :ev, 'agent') "
    "ON CONFLICT (consultant_id, client_id, entity_type, canonical_name) "
    "WHERE client_id IS NOT NULL "
    "DO UPDATE SET "
    "  attributes = kg_entity.attributes || EXCLUDED.attributes, "
    "  confidence = GREATEST(kg_entity.confidence, EXCLUDED.confidence), "
    "  embedding = COALESCE(kg_entity.embedding, EXCLUDED.embedding), "
    "  embed_model = COALESCE(kg_entity.embed_model, EXCLUDED.embed_model), "
    "  embed_dim = COALESCE(kg_entity.embed_dim, EXCLUDED.embed_dim), "
    "  embed_version = COALESCE(kg_entity.embed_version, EXCLUDED.embed_version), "
    "  source_ids = COALESCE((SELECT array_agg(DISTINCT x) FROM unnest("
    "    kg_entity.source_ids || EXCLUDED.source_ids) AS x), kg_entity.source_ids) "
    "RETURNING id, entity_type, confidence"
)


def _embed_params(name_vec: str | None) -> dict[str, Any]:
    return {
        "emb": name_vec,
        "em": embeddings.EMBED_MODEL if name_vec else None,
        "ed": embeddings.EMBED_DIM if name_vec else None,
        "ev": embeddings.EMBED_VERSION if name_vec else None,
    }


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
    name_vec: str | None = None,
    match: entity_resolution.ResolvedEntity | None = None,
    tx: Session | None = None,
) -> str:
    """Scrive una `kg_entity` + il suo nodo outbox.

    `match` (da `entity_resolution.plan_resolution`, gia' deciso fuori dalla
    transazione): se presente, la riga esistente assorbe alias + provenance +
    embedding e ne riusa id/tipo. Se il match e' sparito nel frattempo si
    ricade sull'INSERT. Senza `match` e' l'upsert per nome esatto di sempre.
    """
    attributes = attributes or {}
    with _open(consultant_id, client_id, tx) as session:
        row = None
        if match is not None:
            row = session.execute(
                _MERGE_ENTITY,
                {
                    "alias": entity_resolution.normalize(canonical_name),
                    "attrs": _json(attributes),
                    "conf": confidence,
                    "src": _pg_uuid_array(source_ids),
                    "mid": match.entity_id,
                    **_embed_params(name_vec),
                },
            ).first()
            if row is None:
                logger.warning(
                    "entity resolution: match %s non piu' attivo, inserisco %r",
                    match.entity_id, canonical_name,
                )
            else:
                logger.info(
                    "entity resolution: %r -> %r (%s)",
                    canonical_name, match.canonical_name, match.method,
                )

        if row is None:
            row = session.execute(
                _INSERT_ENTITY,
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
                    **_embed_params(name_vec),
                },
            ).one()

        entity_id = str(row.id)
        # dopo un merge il tipo/confidence autorevoli sono quelli della riga
        # esistente (non declassare 'role' a 'other')
        effective_type = row.entity_type
        effective_conf = float(row.confidence)

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
            "confidence": effective_conf,
            "entity_type": effective_type,
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
    tx: Session | None = None,
) -> str:
    label = _normalize_relation(relation)
    with _open(consultant_id, client_id, tx) as session:
        row = session.execute(
            text(
                "INSERT INTO kg_relation "
                "(consultant_id, client_id, project_id, process_id, scope, "
                " source_entity_id, target_entity_id, relation, evidence, confidence, "
                " confirmed, source_ids, created_by) "
                "VALUES (:c, :cl, :p, :pr, 'client', :s, :t, :rel, :ev, :conf, :cf, "
                "        CAST(:src AS uuid[]), 'agent') "
                "ON CONFLICT (consultant_id, client_id, source_entity_id, target_entity_id, relation) "
                "WHERE client_id IS NOT NULL "
                "DO UPDATE SET "
                "  evidence = EXCLUDED.evidence, "
                "  confidence = GREATEST(kg_relation.confidence, EXCLUDED.confidence), "
                "  confirmed = kg_relation.confirmed OR EXCLUDED.confirmed, "
                "  source_ids = COALESCE((SELECT array_agg(DISTINCT x) FROM unnest("
                "    kg_relation.source_ids || EXCLUDED.source_ids) AS x), kg_relation.source_ids) "
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


# --- Claim / Gap / Contradiction / Impact --------------------------------

def _emit_node(
    session: Session,
    *,
    aggregate_type: str,
    node_id: str,
    label: str,
    id_prop: str,
    props: dict[str, Any],
    consultant_id: str,
    client_id: str | None,
) -> None:
    catalog.assert_projectable(props, context=label)
    _emit(
        session,
        aggregate_type=aggregate_type,
        aggregate_id=node_id,
        consultant_id=consultant_id,
        client_id=client_id,
        payload={
            "kind": "node",
            "label": label,
            "id_prop": id_prop,
            "id_value": node_id,
            "props": props,
        },
    )


def _emit_structural_edge(
    session: Session,
    *,
    aggregate_type: str,
    aggregate_id: str,
    edge_label: str,
    source: tuple[str, str, str],
    target: tuple[str, str, str],
    consultant_id: str,
    client_id: str | None,
) -> None:
    _emit(
        session,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        consultant_id=consultant_id,
        client_id=client_id,
        payload={
            "kind": "edge",
            "label": edge_label,
            "source": {"label": source[0], "id_prop": source[1], "id_value": source[2]},
            "target": {"label": target[0], "id_prop": target[1], "id_value": target[2]},
            "props": {"client_id": str(client_id) if client_id else None},
        },
    )


def write_claim(
    consultant_id: str,
    client_id: str,
    statement: str,
    process_area: str,
    *,
    project_id: str | None = None,
    process_id: str | None = None,
    claim_status: str = "partial",
    linked_element_hint: str | None = None,
    confidence: float = 0.5,
    source_ids: list[str] | None = None,
    tx: Session | None = None,
) -> str:
    process_area = _enum(process_area, _PROCESS_AREAS, "other")
    claim_status = _enum(claim_status, _CLAIM_STATUS, "partial")
    with _open(consultant_id, client_id, tx) as session:
        claim_id = str(
            session.execute(
                text(
                    "INSERT INTO kg_claim "
                    "(consultant_id, client_id, project_id, process_id, scope, "
                    " statement, process_area, claim_status, linked_element_hint, "
                    " confidence, source_ids, created_by) "
                    "VALUES (:c,:cl,:p,:pr,'client',:st,:pa,:cs,:hint,:conf,"
                    "        CAST(:src AS uuid[]),'agent') RETURNING id"
                ),
                {
                    "c": str(consultant_id), "cl": str(client_id),
                    "p": str(project_id) if project_id else None,
                    "pr": str(process_id) if process_id else None,
                    "st": statement, "pa": process_area, "cs": claim_status,
                    "hint": linked_element_hint, "conf": confidence,
                    "src": _pg_uuid_array(source_ids),
                },
            ).one().id
        )
        _emit_node(
            session, aggregate_type="claim", node_id=claim_id, label="Claim",
            id_prop="claim_id", consultant_id=consultant_id, client_id=client_id,
            props={
                "claim_id": claim_id, "client_id": str(client_id),
                "project_id": str(project_id) if project_id else None,
                "layer": "L1", "status": "active", "confidence": confidence,
                "process_area": process_area, "claim_status": claim_status,
                "linked_element_hint": linked_element_hint,
            },
        )
        if process_id:
            _emit_structural_edge(
                session, aggregate_type="claim", aggregate_id=claim_id,
                edge_label="HAS_CLAIM",
                source=("Process", "process_id", str(process_id)),
                target=("Claim", "claim_id", claim_id),
                consultant_id=consultant_id, client_id=client_id,
            )
        return claim_id


def write_gap(
    consultant_id: str,
    client_id: str,
    title: str,
    missing_information: str,
    *,
    project_id: str | None = None,
    process_id: str | None = None,
    required_evidence: str = "",
    severity: str = "medium",
    affected_process_ids: list[str] | None = None,
    confidence: float = 0.5,
    source_ids: list[str] | None = None,
    tx: Session | None = None,
) -> str:
    severity = _enum(severity, _SEVERITY, "medium")
    affected = _pg_uuid_array(affected_process_ids)
    with _open(consultant_id, client_id, tx) as session:
        gap_id = str(
            session.execute(
                text(
                    "INSERT INTO kg_gap "
                    "(consultant_id, client_id, project_id, process_id, scope, "
                    " title, missing_information, required_evidence, severity, "
                    " affected_process_ids, confidence, source_ids, created_by) "
                    "VALUES (:c,:cl,:p,:pr,'client',:t,:mi,:re,:sev,"
                    "        CAST(:aff AS uuid[]),:conf,CAST(:src AS uuid[]),'agent') RETURNING id"
                ),
                {
                    "c": str(consultant_id), "cl": str(client_id),
                    "p": str(project_id) if project_id else None,
                    "pr": str(process_id) if process_id else None,
                    "t": title, "mi": missing_information, "re": required_evidence,
                    "sev": severity, "aff": affected, "conf": confidence,
                    "src": _pg_uuid_array(source_ids),
                },
            ).one().id
        )
        _emit_node(
            session, aggregate_type="gap", node_id=gap_id, label="Gap",
            id_prop="gap_id", consultant_id=consultant_id, client_id=client_id,
            props={
                "gap_id": gap_id, "client_id": str(client_id),
                "project_id": str(project_id) if project_id else None,
                "layer": "L1", "status": "active", "confidence": confidence,
                "severity": severity,
            },
        )
        for target_process in affected or ([str(process_id)] if process_id else []):
            _emit_structural_edge(
                session, aggregate_type="gap", aggregate_id=gap_id, edge_label="BLOCKS",
                source=("Gap", "gap_id", gap_id),
                target=("Process", "process_id", str(target_process)),
                consultant_id=consultant_id, client_id=client_id,
            )
        return gap_id


def write_contradiction(
    consultant_id: str,
    client_id: str,
    title: str,
    *,
    project_id: str | None = None,
    process_id: str | None = None,
    conflicting_claim_ids: list[str] | None = None,
    conflicting_statements: list[str] | None = None,
    resolution_question: str = "",
    severity: str = "medium",
    affected_process_ids: list[str] | None = None,
    confidence: float = 0.5,
    source_ids: list[str] | None = None,
    tx: Session | None = None,
) -> str:
    severity = _enum(severity, _SEVERITY, "medium")
    claim_ids = _pg_uuid_array(conflicting_claim_ids)
    affected = _pg_uuid_array(affected_process_ids)
    with _open(consultant_id, client_id, tx) as session:
        contra_id = str(
            session.execute(
                text(
                    "INSERT INTO kg_contradiction "
                    "(consultant_id, client_id, project_id, process_id, scope, "
                    " title, conflicting_claim_ids, conflicting_statements, "
                    " resolution_question, severity, affected_process_ids, "
                    " confidence, source_ids, created_by) "
                    "VALUES (:c,:cl,:p,:pr,'client',:t,CAST(:cc AS uuid[]),"
                    "        CAST(:cst AS text[]),:rq,:sev,CAST(:aff AS uuid[]),"
                    "        :conf,CAST(:src AS uuid[]),'agent') RETURNING id"
                ),
                {
                    "c": str(consultant_id), "cl": str(client_id),
                    "p": str(project_id) if project_id else None,
                    "pr": str(process_id) if process_id else None,
                    "t": title, "cc": claim_ids,
                    "cst": list(conflicting_statements or []),
                    "rq": resolution_question, "sev": severity, "aff": affected,
                    "conf": confidence, "src": _pg_uuid_array(source_ids),
                },
            ).one().id
        )
        _emit_node(
            session, aggregate_type="contradiction", node_id=contra_id,
            label="Contradiction", id_prop="contradiction_id",
            consultant_id=consultant_id, client_id=client_id,
            props={
                "contradiction_id": contra_id, "client_id": str(client_id),
                "project_id": str(project_id) if project_id else None,
                "layer": "L1", "status": "active", "confidence": confidence,
                "severity": severity,
            },
        )
        for target_process in affected or ([str(process_id)] if process_id else []):
            _emit_structural_edge(
                session, aggregate_type="contradiction", aggregate_id=contra_id,
                edge_label="AFFECTS",
                source=("Contradiction", "contradiction_id", contra_id),
                target=("Process", "process_id", str(target_process)),
                consultant_id=consultant_id, client_id=client_id,
            )
        for claim_id in claim_ids:
            _emit_structural_edge(
                session, aggregate_type="contradiction", aggregate_id=contra_id,
                edge_label="BETWEEN",
                source=("Contradiction", "contradiction_id", contra_id),
                target=("Claim", "claim_id", claim_id),
                consultant_id=consultant_id, client_id=client_id,
            )
        return contra_id


def write_impact(
    consultant_id: str,
    client_id: str,
    title: str,
    impact_area: str,
    mechanism: str,
    *,
    project_id: str | None = None,
    process_id: str | None = None,
    evidence: str = "",
    affected_process_ids: list[str] | None = None,
    confidence: float = 0.5,
    source_ids: list[str] | None = None,
    tx: Session | None = None,
) -> str:
    impact_area = _enum(impact_area, _IMPACT_AREAS, "efficiency")
    affected = _pg_uuid_array(affected_process_ids)
    with _open(consultant_id, client_id, tx) as session:
        impact_id = str(
            session.execute(
                text(
                    "INSERT INTO kg_impact "
                    "(consultant_id, client_id, project_id, process_id, scope, "
                    " title, impact_area, mechanism, evidence, affected_process_ids, "
                    " confidence, source_ids, created_by) "
                    "VALUES (:c,:cl,:p,:pr,'client',:t,:ia,:mech,:ev,"
                    "        CAST(:aff AS uuid[]),:conf,CAST(:src AS uuid[]),'agent') RETURNING id"
                ),
                {
                    "c": str(consultant_id), "cl": str(client_id),
                    "p": str(project_id) if project_id else None,
                    "pr": str(process_id) if process_id else None,
                    "t": title, "ia": impact_area, "mech": mechanism, "ev": evidence,
                    "aff": affected, "conf": confidence,
                    "src": _pg_uuid_array(source_ids),
                },
            ).one().id
        )
        _emit_node(
            session, aggregate_type="impact", node_id=impact_id, label="Impact",
            id_prop="impact_id", consultant_id=consultant_id, client_id=client_id,
            props={
                "impact_id": impact_id, "client_id": str(client_id),
                "project_id": str(project_id) if project_id else None,
                "layer": "L1", "status": "active", "confidence": confidence,
                "impact_area": impact_area,
            },
        )
        for target_process in affected or ([str(process_id)] if process_id else []):
            _emit_structural_edge(
                session, aggregate_type="impact", aggregate_id=impact_id,
                edge_label="AFFECTS",
                source=("Impact", "impact_id", impact_id),
                target=("Process", "process_id", str(target_process)),
                consultant_id=consultant_id, client_id=client_id,
            )
        return impact_id


# --- kg_source + kg_chunk (indice vettoriale, P3) ----------------------

_CHUNK_CHARS = 1600
_CHUNK_OVERLAP = 200


def _chunk_text(content: str) -> list[str]:
    """Split greedy per dimensione, con overlap, spezzando su un confine di
    frase o parola quando possibile. Whitespace normalizzato."""
    normalized = " ".join((content or "").split())
    if not normalized:
        return []
    if len(normalized) <= _CHUNK_CHARS:
        return [normalized]
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = start + _CHUNK_CHARS
        if end < len(normalized):
            cut = normalized.rfind(". ", start + _CHUNK_CHARS // 2, end)
            if cut == -1:
                cut = normalized.rfind(" ", start + _CHUNK_CHARS // 2, end)
            if cut > start:
                end = cut + 1
        piece = normalized[start:end].strip()
        if piece:
            chunks.append(piece)
        start = max(end - _CHUNK_OVERLAP, start + 1)
    return chunks


def prepare_source(content: str) -> tuple[list[str], list[list[float]] | None]:
    """Chunk + embed del testo, SENZA toccare il DB. Da chiamare fuori dalla
    transazione (la chiamata all'embedder e' di rete): `write_evidence` lo fa
    prima di aprire `canonical_session` per non tenere lock durante l'HTTP."""
    chunks = _chunk_text(content)
    vectors = embeddings.embed_texts(chunks) if chunks else None
    return chunks, vectors


def write_source_chunks(
    consultant_id: str,
    client_id: str,
    *,
    title: str,
    content: str,
    kind: str = "note",
    project_id: str | None = None,
    process_id: str | None = None,
    prepared: tuple[list[str], list[list[float]] | None] | None = None,
    tx: Session | None = None,
) -> tuple[str | None, int]:
    """Registra una `kg_source` + i suoi `kg_chunk` (embeddati se possibile).

    `prepared` = output di `prepare_source(content)`; se assente viene
    calcolato qui (comodo per i test / le chiamate singole, ma tiene la
    transazione aperta durante l'embedding).

    Ritorna `(source_id, n_chunk)`. Idempotente sul `content_hash`: se la
    sorgente esiste gia' ritorna il suo id senza re-inserire nulla. Se
    l'embedding non e' disponibile i chunk entrano comunque (tsvector di
    fallback), `embedding` NULL.
    """
    text_value = (content or "").strip()
    if not text_value:
        return None, 0
    kind = _enum(kind, _SOURCE_KINDS, "note")
    content_hash = hashlib.sha256(text_value.encode("utf-8")).hexdigest()
    chunks, vectors = prepared if prepared is not None else prepare_source(text_value)

    with _open(consultant_id, client_id, tx) as session:
        existing = session.execute(
            text(
                "SELECT id FROM kg_source "
                "WHERE consultant_id = :c AND client_id = :cl AND content_hash = :h"
            ),
            {"c": str(consultant_id), "cl": str(client_id), "h": content_hash},
        ).first()
        if existing:
            return str(existing.id), 0

        inserted = session.execute(
            text(
                "INSERT INTO kg_source "
                "(consultant_id, client_id, project_id, process_id, scope, kind, "
                " title, content_hash, byte_size) "
                "VALUES (:c,:cl,:p,:pr,'client',:k,:t,:h,:bs) "
                "ON CONFLICT (consultant_id, client_id, content_hash) "
                "WHERE client_id IS NOT NULL DO NOTHING "
                "RETURNING id"
            ),
            {
                "c": str(consultant_id), "cl": str(client_id),
                "p": str(project_id) if project_id else None,
                "pr": str(process_id) if process_id else None,
                "k": kind, "t": title or "(senza titolo)", "h": content_hash,
                "bs": len(text_value.encode("utf-8")),
            },
        ).first()
        if inserted is None:  # gara: inserita da un'altra transazione
            row = session.execute(
                text(
                    "SELECT id FROM kg_source "
                    "WHERE consultant_id = :c AND client_id = :cl AND content_hash = :h"
                ),
                {"c": str(consultant_id), "cl": str(client_id), "h": content_hash},
            ).first()
            return (str(row.id), 0) if row else (None, 0)
        source_id = str(inserted.id)

        for ordinal, chunk in enumerate(chunks):
            vec = embeddings.to_pgvector(vectors[ordinal]) if vectors else None
            session.execute(
                text(
                    "INSERT INTO kg_chunk "
                    "(source_id, consultant_id, client_id, project_id, ordinal, "
                    " content, embedding, embed_model, embed_dim, embed_version, embedded_at) "
                    "VALUES (:sid,:c,:cl,:p,:ord,:content, CAST(:emb AS vector), "
                    "        :em,:ed,:ev, CASE WHEN :emb IS NULL THEN NULL ELSE now() END)"
                ),
                {
                    "sid": source_id, "c": str(consultant_id), "cl": str(client_id),
                    "p": str(project_id) if project_id else None,
                    "ord": ordinal, "content": chunk, "emb": vec,
                    "em": embeddings.EMBED_MODEL if vec else None,
                    "ed": embeddings.EMBED_DIM if vec else None,
                    "ev": embeddings.EMBED_VERSION if vec else None,
                },
            )
        return source_id, len(chunks)


# --- pacchetto di evidenza (atomico) -----------------------------------

def write_evidence(
    *,
    consultant_id: str,
    client_id: str,
    project_id: str | None = None,
    process_id: str | None = None,
    process_name: str | None = None,
    entities: list[str] | None = None,
    relationships: list[dict] | None = None,
    claims: list[dict] | None = None,
    gaps: list[dict] | None = None,
    contradictions: list[dict] | None = None,
    impacts: list[dict] | None = None,
    source_title: str | None = None,
    source_text: str | None = None,
    source_kind: str = "note",
    resolver_llm: Any | None = None,
) -> dict[str, int]:
    """Scrive un intero pacchetto di evidenza in UNA transazione (fix review #1).

    Tutti gli id di processo (`process_id` e `affected_process_ids` nei dict)
    devono essere gia' canonical. Le entita' delle relazioni sono per nome:
    upsertate una volta, mappa nome->id interna alla transazione.

    Se `source_text` e' passato viene registrata una `kg_source` + i suoi
    `kg_chunk` (indice vettoriale), e il `source_id` risultante finisce nei
    `source_ids` di ogni nodo scritto (provenance).

    Solleva su errore: il chiamante (mirror / cutover) decide se e' fatale.
    """
    counts = {
        "entities": 0, "relationships": 0, "claims": 0,
        "gaps": 0, "contradictions": 0, "impacts": 0, "chunks": 0,
    }
    # chunk + embedding FUORI dalla transazione: la chiamata all'embedder e' di
    # rete e non deve tenere lock sul pacchetto di evidenza atomico.
    has_source = bool(source_text and source_text.strip())
    prepared = prepare_source(source_text) if has_source else None

    # P2: entity resolution decisa FUORI dalla transazione. plan_resolution apre
    # la sua sessione read-only, fa i lookup + le chiamate LLM, la chiude. Il
    # write path qui sotto applica solo il piano (UPSERT deterministico).
    rel_names = [
        n
        for rel in (relationships or [])
        for n in (rel.get("source"), rel.get("target"))
    ]
    resolution = entity_resolution.plan_resolution(
        consultant_id,
        client_id,
        [*(entities or []), *rel_names],
        context=(source_text or "").strip()[:500] or None,
        llm=resolver_llm,
    )

    with canonical_session(consultant_id, client_id) as session:
        source_ids: list[str] | None = None
        if has_source:
            source_id, n_chunks = write_source_chunks(
                consultant_id, client_id,
                title=source_title or "(evidenza)", content=source_text,
                kind=source_kind, project_id=project_id, process_id=process_id,
                prepared=prepared, tx=session,
            )
            if source_id:
                source_ids = [source_id]
                counts["chunks"] = n_chunks

        if process_id and process_name:
            write_process_node(
                consultant_id, client_id, process_id, process_name,
                project_id=project_id, tx=session,
            )

        entity_ids: dict[str, str] = {}

        def _ent(name: Any) -> str:
            display = " ".join(str(name or "").split())
            key = entity_resolution.normalize(display)
            if not key:
                return ""
            if key not in entity_ids:
                match, name_vec = resolution.lookup(display)
                entity_ids[key] = write_entity(
                    consultant_id, client_id, "other", display,
                    project_id=project_id, process_id=process_id,
                    source_ids=source_ids, name_vec=name_vec, match=match,
                    tx=session,
                )
            return entity_ids[key]

        for name in entities or []:
            if _ent(name):
                counts["entities"] += 1

        for rel in relationships or []:
            src, tgt = _ent(rel.get("source")), _ent(rel.get("target"))
            if not src or not tgt:
                continue
            if src == tgt:
                # entity resolution ha mappato entrambi gli estremi sulla stessa
                # entita': kg_relation ha CHECK source <> target, sarebbe un errore.
                logger.info(
                    "relazione %r saltata: estremi risolti alla stessa entita' %s",
                    rel.get("relation"), src,
                )
                continue
            try:
                _normalize_relation(rel.get("relation", ""))
            except ValueError:
                # label di relazione non valida dall'LLM: salta QUESTA relazione,
                # non abortire l'intero pacchetto di evidenza atomico.
                logger.info("relazione saltata: label non valida %r", rel.get("relation"))
                continue
            write_relation(
                consultant_id, client_id, src, rel.get("relation", ""), tgt,
                project_id=project_id, process_id=process_id,
                evidence=rel.get("evidence", "") or "",
                confidence=_float(rel.get("confidence")),
                confirmed=bool(rel.get("confirmed")),
                source_ids=source_ids, tx=session,
            )
            counts["relationships"] += 1

        for claim in claims or []:
            write_claim(
                consultant_id, client_id, claim.get("statement", "") or "",
                claim.get("process_area", "other"),
                project_id=project_id, process_id=process_id,
                claim_status=claim.get("claim_status", "partial"),
                linked_element_hint=claim.get("linked_element_hint"),
                confidence=_float(claim.get("confidence")),
                source_ids=source_ids, tx=session,
            )
            counts["claims"] += 1

        for gap in gaps or []:
            write_gap(
                consultant_id, client_id, gap.get("title", "") or "",
                gap.get("missing_information", "") or "",
                project_id=project_id, process_id=process_id,
                required_evidence=gap.get("required_evidence", "") or "",
                severity=gap.get("severity", "medium"),
                affected_process_ids=gap.get("affected_process_ids"),
                source_ids=source_ids, tx=session,
            )
            counts["gaps"] += 1

        for contra in contradictions or []:
            write_contradiction(
                consultant_id, client_id, contra.get("title", "") or "",
                project_id=project_id, process_id=process_id,
                conflicting_statements=contra.get("conflicting_statements"),
                conflicting_claim_ids=contra.get("conflicting_claim_ids"),
                resolution_question=contra.get("resolution_question", "") or "",
                severity=contra.get("severity", "medium"),
                affected_process_ids=contra.get("affected_process_ids"),
                source_ids=source_ids, tx=session,
            )
            counts["contradictions"] += 1

        for impact in impacts or []:
            write_impact(
                consultant_id, client_id, impact.get("title", "") or "",
                impact.get("impact_area", "efficiency"),
                impact.get("mechanism", "") or "",
                project_id=project_id, process_id=process_id,
                evidence=impact.get("evidence", "") or "",
                affected_process_ids=impact.get("affected_process_ids"),
                confidence=_float(impact.get("confidence")),
                source_ids=source_ids, tx=session,
            )
            counts["impacts"] += 1

    return counts


# --- ingestione asincrona (P5) ---------------------------------------------

EVIDENCE_KEYS = (
    "consultant_id", "client_id", "project_id", "process_id", "process_name",
    "entities", "relationships", "claims", "gaps", "contradictions", "impacts",
    "source_title", "source_text", "source_kind",
)


def enqueue_evidence(
    *,
    consultant_id: str,
    client_id: str,
    project_id: str | None = None,
    process_id: str | None = None,
    process_name: str | None = None,
    entities: list[str] | None = None,
    relationships: list[dict] | None = None,
    claims: list[dict] | None = None,
    gaps: list[dict] | None = None,
    contradictions: list[dict] | None = None,
    impacts: list[dict] | None = None,
    source_title: str | None = None,
    source_text: str | None = None,
    source_kind: str = "note",
) -> int:
    """Accoda il pacchetto di evidenza su `kg_ingest_queue` (P5).

    Il tool ritorna subito; `backend.workers.ingest_worker` drena la coda e
    chiama `write_evidence(**payload)` — embedding + entity resolution + write
    atomico fuori dal giro dell'agente. Ritorna l'id del job. Stessa firma di
    `write_evidence` meno `resolver_llm` (il worker usa l'LLM reale).
    """
    payload = {
        "consultant_id": str(consultant_id),
        "client_id": str(client_id),
        "project_id": str(project_id) if project_id else None,
        "process_id": str(process_id) if process_id else None,
        "process_name": process_name,
        "entities": list(entities or []),
        "relationships": list(relationships or []),
        "claims": list(claims or []),
        "gaps": list(gaps or []),
        "contradictions": list(contradictions or []),
        "impacts": list(impacts or []),
        "source_title": source_title,
        "source_text": source_text,
        "source_kind": source_kind,
    }
    with canonical_session(consultant_id, client_id) as session:
        row = session.execute(
            text(
                "INSERT INTO kg_ingest_queue "
                "(consultant_id, client_id, project_id, process_id, payload) "
                "VALUES (:c, :cl, :p, :pr, CAST(:payload AS jsonb)) RETURNING id"
            ),
            {
                "c": str(consultant_id),
                "cl": str(client_id),
                "p": payload["project_id"],
                "pr": payload["process_id"],
                "payload": _json(payload),
            },
        ).one()
        return int(row.id)


# --- helpers ---------------------------------------------------------------

def _float(value: Any, default: float = 0.5) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return min(1.0, max(0.0, result))


def _pg_uuid_array(ids: list[str] | None) -> list[str]:
    return [str(i) for i in (ids or [])]


def _normalize_relation(relation: str) -> str:
    cleaned = "_".join(str(relation or "").strip().upper().split())
    cleaned = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in cleaned)
    cleaned = cleaned.strip("_")
    if not cleaned or not (cleaned[0].isalpha() or cleaned[0] == "_"):
        raise ValueError(f"label di relazione non valida: {relation!r}")
    return cleaned
