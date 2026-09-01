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

import json
import logging
import secrets
from contextlib import contextmanager
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.db import canonical_session
from backend.memory.knowledge_graph import catalog

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
    tx: Session | None = None,
) -> str:
    attributes = attributes or {}
    with _open(consultant_id, client_id, tx) as session:
        row = session.execute(
            text(
                "INSERT INTO kg_entity "
                "(consultant_id, client_id, project_id, process_id, scope, "
                " entity_type, canonical_name, attributes, source_ids, confidence, created_by) "
                "VALUES (:c, :cl, :p, :pr, 'client', :et, :name, CAST(:attrs AS jsonb), "
                "        CAST(:src AS uuid[]), :conf, 'agent') "
                "ON CONFLICT (consultant_id, client_id, entity_type, canonical_name) "
                "WHERE client_id IS NOT NULL "
                "DO UPDATE SET "
                "  attributes = kg_entity.attributes || EXCLUDED.attributes, "
                "  confidence = GREATEST(kg_entity.confidence, EXCLUDED.confidence), "
                "  source_ids = (SELECT array_agg(DISTINCT x) FROM unnest("
                "    kg_entity.source_ids || EXCLUDED.source_ids) AS x) "
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
                "  source_ids = (SELECT array_agg(DISTINCT x) FROM unnest("
                "    kg_relation.source_ids || EXCLUDED.source_ids) AS x) "
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
) -> dict[str, int]:
    """Scrive un intero pacchetto di evidenza in UNA transazione (fix review #1).

    Tutti gli id di processo (`process_id` e `affected_process_ids` nei dict)
    devono essere gia' canonical. Le entita' delle relazioni sono per nome:
    upsertate una volta, mappa nome->id interna alla transazione.

    Solleva su errore: il chiamante (mirror / cutover) decide se e' fatale.
    """
    counts = {
        "entities": 0, "relationships": 0, "claims": 0,
        "gaps": 0, "contradictions": 0, "impacts": 0,
    }
    with canonical_session(consultant_id, client_id) as session:
        if process_id and process_name:
            write_process_node(
                consultant_id, client_id, process_id, process_name,
                project_id=project_id, tx=session,
            )

        entity_ids: dict[str, str] = {}

        def _ent(name: Any) -> str:
            key = " ".join(str(name or "").split())
            if not key:
                return ""
            if key not in entity_ids:
                entity_ids[key] = write_entity(
                    consultant_id, client_id, "other", key,
                    project_id=project_id, process_id=process_id, tx=session,
                )
            return entity_ids[key]

        for name in entities or []:
            if _ent(name):
                counts["entities"] += 1

        for rel in relationships or []:
            src, tgt = _ent(rel.get("source")), _ent(rel.get("target"))
            if not src or not tgt:
                continue
            write_relation(
                consultant_id, client_id, src, rel.get("relation", ""), tgt,
                project_id=project_id, process_id=process_id,
                evidence=rel.get("evidence", "") or "",
                confidence=_float(rel.get("confidence")),
                confirmed=bool(rel.get("confirmed")),
                tx=session,
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
                tx=session,
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
                tx=session,
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
                tx=session,
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
                tx=session,
            )
            counts["impacts"] += 1

    return counts


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
