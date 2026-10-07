"""`claim_ledger`: il registro dell'evidenza, senza modello di mezzo (INV-9)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from backend.db import canonical_session
from backend.memory import provenance
from backend.services import degradation_counters
from backend.settings import settings
from backend.memory.gateway.scope import ReadScope, _scope_sql, _source_provenance

# --------------------------------------------------------------------------- #
# claim_ledger — il registro dell'evidenza, senza modello di mezzo (INV-9)
# --------------------------------------------------------------------------- #

_LEDGER_SQL = (
    "SELECT c.id, c.statement, c.process_area, c.claim_status, c.confidence, "
    "       c.attributed_to, c.source_name, c.topic, c.assertion, c.qualifiers, "
    "       c.quote, c.quote_verified, "
    "       c.scope_label, c.scope_level, c.epistemic_status, c.source_ids, "
    "       c.process_id, c.created_at "
    "FROM kg_claim c "
    "WHERE c.client_id = :cl AND c.status = 'active'"
)

_CONTRADICTION_SQL = (
    "SELECT title, conflicting_statements, divergence_type, severity, "
    "       resolution_question "
    "FROM kg_contradiction "
    "WHERE client_id = :cl AND status = 'active'"
)


def _contested_topics(session, scope: ReadScope) -> dict[str, list[str]]:
    """I temi su cui esiste una divergenza davvero incompatibile.

    Solo `incompatible` rende conteso un claim. Una differenza di ambito, un
    diverso grado di formalizzazione o un "non lo so" restano registrati come
    divergenze ma non tolgono nulla a cio' che ciascuna fonte ha detto: e' la
    distinzione che nel V3 mancava e che gonfiava ogni attrito in conflitto.
    """
    predicate, params = _scope_sql(scope)
    rows = session.execute(
        text(_CONTRADICTION_SQL + predicate), {"cl": scope.client_id, **params}
    ).all()
    contested: dict[str, list[str]] = {}
    for row in rows:
        if str(row.divergence_type or "") != "incompatible":
            continue
        for statement in row.conflicting_statements or []:
            key = provenance.topic_key(statement)
            if key:
                contested.setdefault(key, []).append(row.title or "")
    return contested


def claim_ledger(
    *,
    consultant_id: str,
    client_id: str,
    scope_project_id: str | None = None,
    scope_process_id: str | None = None,
    allow_client_wide: bool = False,
    limit: int = 200,
) -> dict[str, Any]:
    """Tutte le affermazioni in scope, con la loro provenance e il loro sostegno.

    E' la lettura che rende possibile un audit: ogni riga porta chi lo dice, da
    quale fonte, con quale passaggio verbatim, per quale perimetro, e con un
    `support` **calcolato** (`backend.memory.provenance.build_ledger`) contando
    le voci distinte sullo stesso tema. Nessun modello dichiara qui che una
    cosa e' confermata.

    Stesso confine di `graph_retrieve`: senza scope la chiamata e' rifiutata a
    meno che il chiamante dichiari `allow_client_wide`.
    """
    if not settings.canonical_database_url:
        return {"status": "not_configured", "claims": [], "count": 0}

    scope = ReadScope(
        client_id=str(client_id),
        project_id=scope_project_id,
        process_id=scope_process_id,
        client_wide=allow_client_wide,
    )
    if not scope.narrowed and not allow_client_wide:
        degradation_counters.bump("claim_ledger", "unscoped_call")
        return {
            "status": "blocked", "claims": [], "count": 0,
            "reason": (
                "registro senza scope: serve scope_project_id/scope_process_id, "
                "oppure allow_client_wide=True dichiarato dal chiamante"
            ),
        }

    predicate, params = _scope_sql(scope)
    try:
        with canonical_session(consultant_id, scope.client_id) as session:
            rows = session.execute(
                text(_LEDGER_SQL + predicate + " ORDER BY c.created_at LIMIT :lim"),
                {"cl": scope.client_id, "lim": max(1, int(limit)), **params},
            ).all()
            source_titles = _source_provenance(
                session,
                scope.client_id,
                {str(s) for row in rows for s in (row.source_ids or ())},
            )
            contested = _contested_topics(session, scope)
    except Exception as exc:  # noqa: BLE001 — la lettura non deve far fallire il tool
        degradation_counters.bump("claim_ledger", "error", detail=str(exc))
        return {"status": "error", "claims": [], "count": 0, "reason": str(exc)}

    claims = []
    for row in rows:
        source_id = str(row.source_ids[0]) if row.source_ids else None
        claims.append(
            {
                "claim_id": str(row.id),
                "statement": row.statement,
                "attributed_to": row.attributed_to or "",
                # Il titolo autoritativo della `kg_source` batte il nome che
                # l'estrazione ha dichiarato: e' quello che il consulente puo'
                # aprire.
                "source_name": (
                    source_titles.get(source_id, ("", None))[0]
                    if source_id
                    else ""
                ) or (row.source_name or ""),
                "source_id": source_id,
                "topic": row.topic or "",
                "assertion": row.assertion or "",
                "qualifiers": list(row.qualifiers or ()),
                "quote": row.quote or "",
                "quote_verified": bool(row.quote_verified),
                "scope_label": row.scope_label or "",
                "scope_level": row.scope_level or "stated_scope",
                "epistemic_status": row.epistemic_status or "reported",
                "process_area": row.process_area or "other",
                "process_id": str(row.process_id) if row.process_id else None,
            }
        )

    # Una contraddizione cita le affermazioni in conflitto per testo, non per
    # tema: qui si risale dal testo al tema del claim, altrimenti la
    # classificazione resta scritta e non arriva mai al registro.
    by_statement = {}
    for item in claims:
        assertion = provenance.topic_key(item["assertion"] or item["statement"])
        for written in (item["statement"], item["topic"], item["assertion"]):
            key = provenance.topic_key(written)
            if key:
                by_statement.setdefault(key, assertion)
    for key, titles in list(contested.items()):
        mapped = by_statement.get(key)
        if mapped and mapped != key:
            contested.setdefault(mapped, []).extend(titles)

    entries = provenance.build_ledger(claims, contested_topics=contested)
    payload = provenance.ledger_payload(entries)
    return {
        "status": "ok" if payload else "empty",
        "count": len(payload),
        "claims": payload,
        "summary": provenance.summarize_ledger(entries).as_dict(),
        "contested_topics": sorted(contested),
    }
