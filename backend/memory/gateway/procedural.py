"""`procedural_retrieve`: i playbook appresi 'active', scoped (INV-9 / INV-12)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from backend.db import canonical_session
from backend.services import degradation_counters
from backend.memory.gateway.scope import _WORD, procedural_available

# --------------------------------------------------------------------------- #
# procedural_retrieve — playbook appresi 'active', scoped (INV-9 / INV-12)
# --------------------------------------------------------------------------- #

_PROCEDURAL_KINDS = ("playbook", "heuristic", "checklist")


def _rank_playbooks(rows: list, task_text: str) -> list:
    """Ranking lessicale: sovrapposizione di parole tra `task_text` e
    `title` + `applies_when`. A parita' preferisce il playbook client-scoped
    (piu' specifico) e poi la confidence."""
    terms = {w.lower() for w in _WORD.findall(task_text or "")}
    scored = []
    for row in rows:
        haystack = f"{row.title or ''} {row.applies_when or ''}".lower()
        overlap = len(terms & {w.lower() for w in _WORD.findall(haystack)})
        scored.append((overlap, 1 if row.client_id else 0, float(row.confidence or 0.0), row))
    scored.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    return [item[3] for item in scored]


def procedural_retrieve(
    *,
    consultant_id: str,
    client_id: str | None = None,
    task_text: str = "",
    kinds: list[str] | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """Playbook appresi `active` pertinenti al task, con lo scope iniettato.

    RLS fa il grosso: aperto `canonical_session(consultant_id, client_id)`, i
    playbook consultant-scoped (`client_id IS NULL`) sono sempre visibili,
    quelli client-scoped solo nel loro cliente. Aperto senza `client_id` si
    vedono solo i consultant-scoped.

    Ritorna `{"status": ok|empty|not_configured|error, "count", "playbooks"}`.
    """
    if not procedural_available():
        return {"status": "not_configured", "playbooks": [], "count": 0}

    wanted = [k for k in (kinds or _PROCEDURAL_KINDS) if k in _PROCEDURAL_KINDS]
    if not wanted:
        wanted = list(_PROCEDURAL_KINDS)

    try:
        with canonical_session(consultant_id, client_id) as session:
            rows = session.execute(
                text(
                    "SELECT id, scope, kind, title, applies_when, body, confidence, client_id "
                    "FROM procedural_memory "
                    "WHERE status = 'active' AND kind = ANY(:kinds) "
                    "ORDER BY confidence DESC, updated_at DESC LIMIT 60"
                ),
                {"kinds": wanted},
            ).all()
    except Exception as exc:  # noqa: BLE001 — la lettura non deve far fallire il tool
        degradation_counters.bump("procedural_retrieve", "error", detail=str(exc))
        return {"status": "error", "playbooks": [], "count": 0, "reason": str(exc)}

    ranked = _rank_playbooks(rows, task_text)[: max(1, limit)]
    playbooks = [
        {
            "id": str(row.id),
            "scope": row.scope,
            "kind": row.kind,
            "title": row.title,
            "applies_when": row.applies_when,
            "body": row.body,
            "confidence": float(row.confidence or 0.0),
            "client_scoped": bool(row.client_id),
        }
        for row in ranked
    ]
    return {
        "status": "ok" if playbooks else "empty",
        "count": len(playbooks),
        "playbooks": playbooks,
    }
