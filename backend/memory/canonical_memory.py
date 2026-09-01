"""Scrittura canonical della memoria (semantic / episodic) + emit del log Mem0.

INSERT nella tabella Postgres + riga `mem0_projection_log` nella STESSA
transazione `canonical_session` (ruolo delir_app: RLS + INSERT-only sulla log).
`backend/workers/mem0_worker.py` applichera' poi a Mem0 OSS.

Scope: 'client' se `client_id` e' passato, altrimenti 'consultant'.
user_id di Mem0 = consultant_id; il client_id viaggia nei metadata (filtro in
ricerca lato gateway).

Procedural memory non e' qui: le skill spedite stanno nel repo, i playbook
appresi arriveranno col learning flow (P7).
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.db import canonical_session


def _scope(client_id: str | None) -> str:
    return "client" if client_id else "consultant"


def _emit_mem0(
    session: Session,
    *,
    memory_kind: str,
    memory_id: str,
    consultant_id: str,
    client_id: str | None,
    text_value: str,
    metadata: dict[str, Any],
    source_ids: list[str] | None,
    op: str = "add",
) -> None:
    payload = {
        "text": text_value,
        "user_id": str(consultant_id),
        "metadata": metadata,
    }
    session.execute(
        text(
            "INSERT INTO mem0_projection_log "
            "(memory_kind, memory_id, consultant_id, client_id, op, mem0_payload, source_ids) "
            "VALUES (:k, :mid, :c, :cl, :op, CAST(:p AS jsonb), CAST(:src AS uuid[]))"
        ),
        {
            "k": memory_kind,
            "mid": memory_id,
            "c": str(consultant_id),
            "cl": str(client_id) if client_id else None,
            "op": op,
            "p": json.dumps(payload, default=str),
            "src": [str(s) for s in (source_ids or [])],
        },
    )


def write_semantic_memory(
    consultant_id: str,
    *,
    kind: str,
    statement: str,
    client_id: str | None = None,
    project_id: str | None = None,
    process_id: str | None = None,
    subject: str | None = None,
    category: str | None = None,
    confidence: float = 0.5,
    source_ids: list[str] | None = None,
) -> str:
    with canonical_session(consultant_id, client_id) as session:
        memory_id = str(
            session.execute(
                text(
                    "INSERT INTO semantic_memory "
                    "(consultant_id, client_id, project_id, process_id, scope, kind, "
                    " statement, subject, category, confidence, source_ids, created_by) "
                    "VALUES (:c,:cl,:p,:pr,:sc,:k,:st,:sub,:cat,:conf,"
                    "        CAST(:src AS uuid[]),'agent') RETURNING id"
                ),
                {
                    "c": str(consultant_id),
                    "cl": str(client_id) if client_id else None,
                    "p": str(project_id) if project_id else None,
                    "pr": str(process_id) if process_id else None,
                    "sc": _scope(client_id),
                    "k": kind,
                    "st": statement,
                    "sub": subject,
                    "cat": category,
                    "conf": confidence,
                    "src": [str(s) for s in (source_ids or [])],
                },
            ).one().id
        )
        _emit_mem0(
            session,
            memory_kind="semantic",
            memory_id=memory_id,
            consultant_id=consultant_id,
            client_id=client_id,
            text_value=statement,
            metadata={
                "memory_kind": "semantic",
                "memory_id": memory_id,
                "consultant_id": str(consultant_id),
                "client_id": str(client_id) if client_id else None,
                "kind": kind,
                "category": category,
            },
            source_ids=source_ids,
        )
        return memory_id


def write_episodic_memory(
    consultant_id: str,
    *,
    episode_type: str,
    title: str,
    client_id: str | None = None,
    project_id: str | None = None,
    process_id: str | None = None,
    summary: str | None = None,
    occurred_at: datetime | str | None = None,
    participants: list[str] | None = None,
    raw_source_id: str | None = None,
    confidence: float = 0.5,
    source_ids: list[str] | None = None,
) -> str:
    with canonical_session(consultant_id, client_id) as session:
        memory_id = str(
            session.execute(
                text(
                    "INSERT INTO episodic_memory "
                    "(consultant_id, client_id, project_id, process_id, scope, "
                    " episode_type, title, summary, occurred_at, participants, "
                    " raw_source_id, confidence, source_ids, created_by) "
                    "VALUES (:c,:cl,:p,:pr,:sc,:et,:t,:sum,:occ,"
                    "        CAST(:part AS text[]),:rsid,:conf,CAST(:src AS uuid[]),'agent') "
                    "RETURNING id"
                ),
                {
                    "c": str(consultant_id),
                    "cl": str(client_id) if client_id else None,
                    "p": str(project_id) if project_id else None,
                    "pr": str(process_id) if process_id else None,
                    "sc": _scope(client_id),
                    "et": episode_type,
                    "t": title,
                    "sum": summary,
                    "occ": occurred_at,
                    "part": list(participants or []),
                    "rsid": str(raw_source_id) if raw_source_id else None,
                    "conf": confidence,
                    "src": [str(s) for s in (source_ids or [])],
                },
            ).one().id
        )
        _emit_mem0(
            session,
            memory_kind="episodic",
            memory_id=memory_id,
            consultant_id=consultant_id,
            client_id=client_id,
            text_value=summary or title,
            metadata={
                "memory_kind": "episodic",
                "memory_id": memory_id,
                "consultant_id": str(consultant_id),
                "client_id": str(client_id) if client_id else None,
                "episode_type": episode_type,
                "title": title,
            },
            source_ids=source_ids,
        )
        return memory_id
