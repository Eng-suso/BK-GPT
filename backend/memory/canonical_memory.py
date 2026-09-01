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
import logging
from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.db import canonical_session

logger = logging.getLogger(__name__)


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
    already_applied: bool = False,
    applied_mem0_id: str | None = None,
) -> None:
    """Scrive la riga di log per il worker Mem0.

    `already_applied=True` quando il chiamante ha gia' fatto la add/search
    sincrona su Mem0 (vedi semantic_store / episodic_store): la riga nasce
    gia' `applied_at = now()` (+ `mem0_memory_id` se noto) — e' solo l'audit
    trail, il worker non deve rifare nulla. Altrimenti resta pending per
    backend.workers.mem0_worker.
    """
    payload = {
        "text": text_value,
        "user_id": str(consultant_id),
        "metadata": metadata,
    }
    session.execute(
        text(
            "INSERT INTO mem0_projection_log "
            "(memory_kind, memory_id, consultant_id, client_id, op, mem0_payload, "
            " source_ids, mem0_memory_id, applied_at) "
            "VALUES (:k, :mid, :c, :cl, :op, CAST(:p AS jsonb), CAST(:src AS uuid[]), "
            "        :appmid, CASE WHEN :already THEN now() ELSE NULL END)"
        ),
        {
            "appmid": applied_mem0_id,
            "already": already_applied,
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
    already_applied_mem0_id: str | None = None,
) -> str:
    """`already_applied_mem0_id`: passalo quando hai gia' chiamato Mem0 in modo
    sincrono (es. semantic_store) — il log nasce gia' applicato, il worker non
    ripete la add."""
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
            already_applied=already_applied_mem0_id is not None,
            applied_mem0_id=already_applied_mem0_id,
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
    already_applied_mem0_id: str | None = None,
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
            already_applied=already_applied_mem0_id is not None,
            applied_mem0_id=already_applied_mem0_id,
        )
        return memory_id


# --------------------------------------------------------------------------- #
# procedural memory — playbook appresi del consulente (L2 / INV-11/12/13)
# --------------------------------------------------------------------------- #
#
# Le skill spedite restano nel repo/git (INV-12): NON entrano qui. Questa
# tabella tiene solo i metodi appresi lavorando col consulente. Un playbook
# nasce `candidate` (fuori dal runtime) e diventa `active` solo dopo il
# guardrail (`backend.memory.procedural.guardrail`), che il gate DB
# (`procedural_guardrail_gate`) rende obbligatorio.

_PROCEDURAL_KINDS = frozenset({"playbook", "heuristic", "checklist"})
_CREATED_BY = frozenset({"agent", "consultant", "migration"})


def _jsonable(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _procedural_row(row: Any) -> dict[str, Any]:
    return {key: _jsonable(val) for key, val in row._mapping.items()}


def write_procedural_candidate(
    consultant_id: str,
    *,
    kind: str,
    title: str,
    body: str,
    applies_when: str | None = None,
    scope: str = "client",
    client_id: str | None = None,
    project_id: str | None = None,
    derived_from: list[str] | None = None,
    source_ids: list[str] | None = None,
    confidence: float = 0.5,
    created_by: str = "agent",
    supersedes_id: str | None = None,
) -> str:
    """INSERT di un playbook appreso in stato `candidate` (non attivo).

    scope `client` -> `client_id` obbligatorio; scope `consultant` -> `client_id`
    None (generalizzato, INV-13). `guardrail_status` nasce `pending`:
    `promote_procedural` lo valida prima di portare la riga ad `active`.

    Con `supersedes_id` la riga eredita `lineage_id` e prende `version+1` della
    riga superata: e' la nuova versione di un playbook esistente (P7.4), non una
    lineage nuova.
    """
    scope = "consultant" if scope == "consultant" else "client"
    if scope == "consultant":
        client_id = None
    elif not client_id:
        raise ValueError("scope 'client' richiede client_id")
    if kind not in _PROCEDURAL_KINDS:
        raise ValueError(f"kind procedurale non valido: {kind!r}")
    if not (title or "").strip() or not (body or "").strip():
        raise ValueError("title e body sono obbligatori")

    with canonical_session(consultant_id, client_id) as session:
        lineage_id: str | None = None
        version = 1
        if supersedes_id:
            prev = session.execute(
                text(
                    "SELECT lineage_id, version FROM procedural_memory WHERE id = :i"
                ),
                {"i": str(supersedes_id)},
            ).first()
            if prev is not None:
                lineage_id = str(prev.lineage_id)
                version = int(prev.version) + 1

        row = session.execute(
            text(
                "INSERT INTO procedural_memory "
                "(consultant_id, client_id, project_id, scope, kind, title, "
                " applies_when, body, status, confidence, version, lineage_id, "
                " supersedes_id, guardrail_status, source_ids, derived_from, created_by) "
                "VALUES (:c,:cl,:p,:sc,:k,:t,:aw,:b,'candidate',:conf,:ver,"
                "        COALESCE(CAST(:lin AS uuid), gen_random_uuid()), "
                "        CAST(:sup AS uuid),'pending', "
                "        CAST(:src AS uuid[]), CAST(:df AS uuid[]), :cb) "
                "RETURNING id"
            ),
            {
                "c": str(consultant_id),
                "cl": str(client_id) if client_id else None,
                "p": str(project_id) if project_id else None,
                "sc": scope,
                "k": kind,
                "t": title,
                "aw": applies_when,
                "b": body,
                "conf": min(1.0, max(0.0, float(confidence))),
                "ver": version,
                "lin": lineage_id,
                "sup": str(supersedes_id) if supersedes_id else None,
                "src": [str(s) for s in (source_ids or [])],
                "df": [str(d) for d in (derived_from or [])],
                "cb": created_by if created_by in _CREATED_BY else "agent",
            },
        ).one()
        return str(row.id)


def get_procedural(
    memory_id: str,
    *,
    consultant_id: str,
    client_id: str | None = None,
) -> dict[str, Any] | None:
    """Dettaglio di una riga `procedural_memory` (RLS applicata dallo scope)."""
    with canonical_session(consultant_id, client_id) as session:
        row = session.execute(
            text(
                "SELECT id, scope, kind, title, applies_when, body, status, "
                " confidence, guardrail_status, version, lineage_id, supersedes_id, "
                " derived_from, source_ids, project_id, client_id, created_by, "
                " created_at, updated_at, activated_at, used_count, last_used_at, "
                " outcome_worked, outcome_partial, outcome_failed, last_outcome_at "
                "FROM procedural_memory WHERE id = :i"
            ),
            {"i": str(memory_id)},
        ).first()
        return _procedural_row(row) if row is not None else None


def promote_procedural(
    candidate_id: str,
    *,
    consultant_id: str,
    client_id: str | None = None,
    llm: Any | None = None,
) -> dict[str, Any]:
    """`candidate` -> `active`, previo guardrail.

    Verdetto del guardrail scritto in `guardrail_status`. Se non e' `clean` la
    riga resta `candidate` (e il gate DB impedisce comunque l'attivazione).
    Se `clean`: deprecata l'eventuale `active` dello stesso `lineage_id`, la
    riga passa `active` con `activated_at = now()` (una sola active per lineage,
    indice UNIQUE `procedural_one_active`).

    Per scope `consultant` il guardrail verifica anche che nessun nome cliente
    del consulente sia rimasto nel corpo (generalizzazione non completa, INV-13).
    """
    from backend.memory.procedural import guardrail

    with canonical_session(consultant_id, client_id) as session:
        row = session.execute(
            text(
                "SELECT id, scope, kind, title, applies_when, body, status, lineage_id "
                "FROM procedural_memory WHERE id = :i"
            ),
            {"i": str(candidate_id)},
        ).first()
        if row is None:
            return {"status": "not_found", "id": str(candidate_id)}
        if row.status == "active":
            return {"status": "already_active", "id": str(candidate_id)}
        if row.status in {"deprecated", "rejected"}:
            return {
                "status": "blocked",
                "id": str(candidate_id),
                "reason": f"status {row.status}",
            }

        client_names: list[str] = []
        if row.scope == "consultant":
            client_names = [
                str(r.name)
                for r in session.execute(text("SELECT name FROM client")).all()
                if r.name
            ]  # contesto consultant-only: la RLS strict-client li mostra tutti

        guardrail_status, findings = guardrail.check(
            body=row.body,
            title=row.title,
            applies_when=row.applies_when,
            scope=row.scope,
            client_names=client_names,
            llm=llm,
        )
        session.execute(
            text(
                "UPDATE procedural_memory SET guardrail_status = :g WHERE id = :i"
            ),
            {"g": guardrail_status, "i": str(candidate_id)},
        )
        if guardrail_status != "clean":
            return {
                "status": "guardrail_flagged",
                "id": str(candidate_id),
                "guardrail_status": guardrail_status,
                "findings": findings,
            }

        session.execute(
            text(
                "UPDATE procedural_memory SET status = 'deprecated' "
                "WHERE lineage_id = :lin AND status = 'active' AND id <> :i"
            ),
            {"lin": str(row.lineage_id), "i": str(candidate_id)},
        )
        session.execute(
            text(
                "UPDATE procedural_memory "
                "SET status = 'active', activated_at = now() WHERE id = :i"
            ),
            {"i": str(candidate_id)},
        )
        return {
            "status": "promoted",
            "id": str(candidate_id),
            "guardrail_status": "clean",
        }


def deprecate_procedural(
    memory_id: str,
    *,
    consultant_id: str,
    client_id: str | None = None,
) -> dict[str, Any]:
    """Ritira un playbook: `status='deprecated'` (idempotente)."""
    with canonical_session(consultant_id, client_id) as session:
        result = session.execute(
            text(
                "UPDATE procedural_memory SET status = 'deprecated' "
                "WHERE id = :i AND status <> 'deprecated'"
            ),
            {"i": str(memory_id)},
        )
        return {
            "status": "deprecated" if result.rowcount else "noop",
            "id": str(memory_id),
        }


# outcome normalizzato -> colonna contatore
_OUTCOME_COLUMN = {
    "worked": "outcome_worked",
    "partial": "outcome_partial",
    "didn't_work": "outcome_failed",
    "didnt_work": "outcome_failed",
    "failed": "outcome_failed",
}
# confidence = ratio di successo smussato (media mobile su TUTTI gli esiti):
#   (worked + 0.5*partial + prior) / (worked + partial + failed + prior_weight)
_CONFIDENCE_PRIOR = 0.5
_CONFIDENCE_PRIOR_WEIGHT = 1.0
_AUTO_DEPRECATE_CONFIDENCE = 0.2
_AUTO_DEPRECATE_FAILURES = 3


def _blended_confidence(worked: int, partial: int, failed: int) -> float:
    numerator = worked + 0.5 * partial + _CONFIDENCE_PRIOR
    denominator = worked + partial + failed + _CONFIDENCE_PRIOR_WEIGHT
    return min(1.0, max(0.0, numerator / denominator))


def record_playbook_usage(
    consultant_id: str,
    *,
    client_id: str | None = None,
    playbook_ids: list[str],
) -> int:
    """Segna che questi playbook `active` sono stati iniettati nel prompt
    (`used_count += 1`, `last_used_at = now()`). Best-effort: ritorna quante
    righe ha toccato, 0 su qualsiasi problema."""
    ids = sorted({str(p) for p in (playbook_ids or []) if p})
    if not ids:
        return 0
    try:
        with canonical_session(consultant_id, client_id) as session:
            result = session.execute(
                text(
                    "UPDATE procedural_memory "
                    "SET used_count = used_count + 1, last_used_at = now() "
                    "WHERE id = ANY(:ids) AND status = 'active'"
                ),
                {"ids": ids},
            )
            return int(result.rowcount or 0)
    except Exception:  # noqa: BLE001 — il conteggio non deve mai rompere il turno
        logger.warning("record_playbook_usage fallito", exc_info=True)
        return 0


def record_playbook_outcome(
    playbook_id: str,
    outcome: str,
    *,
    consultant_id: str,
    client_id: str | None = None,
) -> dict[str, Any]:
    """Registra l'esito d'uso di un playbook (`worked` | `partial` | `didn't_work`).

    Incrementa il contatore e ricalcola `confidence` come ratio di successo
    smussato su tutti gli esiti registrati:
    `(worked + 0.5*partial + prior) / (worked + partial + failed + prior_weight)`.
    Se la confidence scende sotto `_AUTO_DEPRECATE_CONFIDENCE` con almeno
    `_AUTO_DEPRECATE_FAILURES` esiti negativi, auto-depreca il playbook
    (`status='deprecated'`).
    """
    key = (outcome or "").strip().lower()
    column = _OUTCOME_COLUMN.get(key)
    if column is None:
        return {"status": "bad_outcome", "id": str(playbook_id), "outcome": outcome}

    with canonical_session(consultant_id, client_id) as session:
        row = session.execute(
            text(
                "SELECT status, outcome_worked, outcome_partial, outcome_failed "
                "FROM procedural_memory WHERE id = :i"
            ),
            {"i": str(playbook_id)},
        ).first()
        if row is None:
            return {"status": "not_found", "id": str(playbook_id)}

        worked = int(row.outcome_worked) + (1 if column == "outcome_worked" else 0)
        partial = int(row.outcome_partial) + (1 if column == "outcome_partial" else 0)
        failures = int(row.outcome_failed) + (1 if column == "outcome_failed" else 0)
        new_confidence = _blended_confidence(worked, partial, failures)
        auto_deprecate = (
            row.status == "active"
            and new_confidence < _AUTO_DEPRECATE_CONFIDENCE
            and failures >= _AUTO_DEPRECATE_FAILURES
        )
        session.execute(
            text(
                f"UPDATE procedural_memory "
                f"SET {column} = {column} + 1, "
                f"    confidence = :conf, "
                f"    last_outcome_at = now()"
                + (", status = 'deprecated'" if auto_deprecate else "")
                + " WHERE id = :i"
            ),
            {"conf": new_confidence, "i": str(playbook_id)},
        )
        return {
            "status": "recorded",
            "id": str(playbook_id),
            "outcome": key,
            "confidence": round(new_confidence, 4),
            "auto_deprecated": auto_deprecate,
        }


def list_episodes_for_learning(
    consultant_id: str,
    *,
    client_id: str | None = None,
    project_id: str | None = None,
    limit: int = 12,
) -> list[dict[str, Any]]:
    """Episodi `active` recenti per il pattern extraction (P7.2), scope via RLS."""
    with canonical_session(consultant_id, client_id) as session:
        rows = session.execute(
            text(
                "SELECT id, episode_type, title, summary, occurred_at "
                "FROM episodic_memory "
                "WHERE status = 'active' "
                "  AND (CAST(:pid AS uuid) IS NULL OR project_id = CAST(:pid AS uuid)) "
                "ORDER BY COALESCE(occurred_at, created_at) DESC "
                "LIMIT :lim"
            ),
            {
                "pid": str(project_id) if project_id else None,
                "lim": max(1, min(int(limit), 50)),
            },
        ).all()
    return [
        {
            "id": str(row.id),
            "episode_type": row.episode_type,
            "title": row.title,
            "summary": row.summary,
            "occurred_at": _jsonable(row.occurred_at),
        }
        for row in rows
    ]


def list_client_names(consultant_id: str) -> list[str]:
    """Nomi di tutti i clienti del consulente (contesto consultant-only:
    la RLS strict-client li mostra tutti). Usato dal guardrail / generalizzazione."""
    with canonical_session(consultant_id) as session:
        return [
            str(row.name)
            for row in session.execute(text("SELECT name FROM client")).all()
            if row.name
        ]


def generalize_procedural(
    source_id: str,
    *,
    consultant_id: str,
    client_id: str,
    llm: Any | None = None,
) -> dict[str, Any]:
    """Promozione client -> consultant come GENERALIZZAZIONE, non copia (INV-13).

    Legge il playbook client-scoped `source_id`, lo fa riscrivere come metodo
    generico (nomi cliente e dati riservati rimossi) e crea un NUOVO
    `procedural_memory` scope='consultant', `client_id=NULL`, status='candidate',
    `derived_from=[source_id]`, `guardrail_status='pending'`.

    Non attiva nulla: `promote_procedural` sul nuovo candidate fa girare il
    guardrail, che blocca la promozione se un nome cliente e' sopravvissuto.
    """
    from backend.memory.procedural import extraction

    with canonical_session(consultant_id, client_id) as session:
        row = session.execute(
            text(
                "SELECT id, scope, kind, title, applies_when, body "
                "FROM procedural_memory WHERE id = :i"
            ),
            {"i": str(source_id)},
        ).first()
    if row is None:
        return {"status": "not_found", "id": str(source_id)}
    if row.scope != "client":
        return {"status": "blocked", "id": str(source_id), "reason": "il sorgente non e' client-scoped"}

    generalized = extraction.generalize_playbook_body(
        {"title": row.title, "applies_when": row.applies_when, "body": row.body},
        list_client_names(consultant_id),
        llm=llm,
    )
    if generalized is None:
        return {"status": "no_method", "id": str(source_id)}

    candidate_id = write_procedural_candidate(
        consultant_id,
        kind=row.kind,
        title=generalized.title,
        body=generalized.body,
        applies_when=generalized.applies_when or None,
        scope="consultant",
        derived_from=[str(source_id)],
        created_by="agent",
    )
    return {
        "status": "generalized",
        "source_id": str(source_id),
        "candidate_id": candidate_id,
    }


def procedural_candidate_for_episodes(
    consultant_id: str,
    *,
    client_id: str | None = None,
    episode_ids: list[str],
) -> str | None:
    """Id di un playbook (non `rejected`) gia' derivato ESATTAMENTE da questo set
    di episodi — dedup per il pattern extraction (P7.2)."""
    ids = sorted({str(e) for e in (episode_ids or []) if e})
    if not ids:
        return None
    with canonical_session(consultant_id, client_id) as session:
        row = session.execute(
            text(
                "SELECT id FROM procedural_memory "
                "WHERE status <> 'rejected' "
                "  AND derived_from @> CAST(:ids AS uuid[]) "
                "  AND derived_from <@ CAST(:ids AS uuid[]) "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"ids": ids},
        ).first()
    return str(row.id) if row is not None else None
