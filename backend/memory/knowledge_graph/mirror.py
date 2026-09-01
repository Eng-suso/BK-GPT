"""Traduce l'evidenza estratta dai toolset (project_memory / process_memory)
nello schema canonical e la scrive.

E' l'UNICO percorso di scrittura del knowledge graph dai toolset (cutover
"Cervello DeliR"): risolve lo scope workspace -> canonical, adatta i modelli
pydantic dei tool a dict, e chiama `canonical.write_evidence`. Se il tool
passa `raw_content`, il testo diventa una `kg_source` + `kg_chunk` embeddati
(indice vettoriale, P3) e la sua provenance finisce nei nodi scritti.

Best-effort e non bloccante: se il canonical non e' configurato, o lo scope
non si risolve, o la scrittura fallisce, si registra e si va avanti. Il
chiamante (un tool di salvataggio evidenza) non deve mai fallire per colpa
di questo modulo.

L'intero pacchetto di evidenza va in UNA transazione via
`canonical.write_evidence` (fix review #1): o tutto o niente.
"""

from __future__ import annotations

import logging
from typing import Any

from backend.memory import scope as scope_module
from backend.memory.knowledge_graph import canonical
from backend.settings import settings

logger = logging.getLogger(__name__)

_CONFIDENCE_WORDS = {"low": 0.3, "medium": 0.6, "high": 0.9, "unknown": 0.5}


def enabled() -> bool:
    return bool(settings.canonical_database_url and settings.canonical_ingest_mirror)


def _conf(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return _CONFIDENCE_WORDS.get(str(value or "").lower(), 0.5)


def _get(obj: Any, name: str, default: Any = None) -> Any:
    return getattr(obj, name, default)


def mirror_evidence(
    *,
    workspace_project_id: str,
    workspace_process_ids: list[str] | None = None,
    entities: list[str] | None = None,
    relationships: list | None = None,
    claims: list | None = None,
    gaps: list | None = None,
    contradictions: list | None = None,
    impacts: list | None = None,
    raw_content: str | None = None,
    source_title: str | None = None,
) -> dict[str, Any]:
    if not enabled():
        return {"mirrored": False, "reason": "disabled"}

    process_ids = [p for p in (workspace_process_ids or []) if p]
    process_scope: dict[str, scope_module.ScopeIds] = {}

    try:
        base_scope = scope_module.resolve(
            workspace_project_id, process_ids[0] if process_ids else None
        )
        if process_ids:
            process_scope[process_ids[0]] = base_scope
        for wpid in process_ids[1:]:
            process_scope[wpid] = scope_module.resolve(workspace_project_id, wpid)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "canonical mirror: scope non risolvibile per %s (%s)", workspace_project_id, exc
        )
        return {"mirrored": False, "reason": str(exc)}

    def _canon_processes(workspace_ids: list[str] | None) -> list[str]:
        resolved = []
        for wpid in workspace_ids or []:
            s = process_scope.get(wpid)
            if s is None:
                try:
                    s = scope_module.resolve(workspace_project_id, wpid)
                    process_scope[wpid] = s
                except Exception:  # noqa: BLE001
                    continue
            if s.process_id:
                resolved.append(s.process_id)
        return resolved or ([base_scope.process_id] if base_scope.process_id else [])

    rel_dicts = [
        {
            "source": _get(r, "source"),
            "relation": _get(r, "relation"),
            "target": _get(r, "target"),
            "evidence": _get(r, "evidence", ""),
            "confidence": _conf(_get(r, "confidence")),
            "confirmed": bool(_get(r, "confirmed")),
        }
        for r in relationships or []
    ]
    claim_dicts = [
        {
            "statement": _get(c, "claim"),
            "process_area": _get(c, "process_area", "other"),
            "claim_status": _get(c, "status", "partial"),
            "linked_element_hint": _get(c, "linked_element_hint"),
            "confidence": _conf(_get(c, "confidence")),
        }
        for c in claims or []
    ]
    gap_dicts = [
        {
            "title": _get(g, "title"),
            "missing_information": _get(g, "missing_information", ""),
            "required_evidence": _get(g, "required_evidence", ""),
            "severity": _get(g, "severity", "medium"),
            "affected_process_ids": _canon_processes(_get(g, "affected_process_ids")),
        }
        for g in gaps or []
    ]
    contra_dicts = [
        {
            "title": _get(c, "title"),
            "conflicting_statements": list(_get(c, "conflicting_claims", []) or []),
            "resolution_question": _get(c, "resolution_question", ""),
            "severity": _get(c, "severity", "medium"),
            "affected_process_ids": _canon_processes(_get(c, "affected_process_ids")),
        }
        for c in contradictions or []
    ]
    impact_dicts = [
        {
            "title": _get(i, "title"),
            "impact_area": _get(i, "impact_area", "efficiency"),
            "mechanism": _get(i, "mechanism", ""),
            "evidence": _get(i, "evidence", ""),
            "confidence": _conf(_get(i, "confidence")),
            "affected_process_ids": _canon_processes(_get(i, "affected_process_ids")),
        }
        for i in impacts or []
    ]

    scope_out = {
        "consultant_id": base_scope.consultant_id,
        "client_id": base_scope.client_id,
        "project_id": base_scope.project_id,
        "process_id": base_scope.process_id,
    }

    try:
        counts = canonical.write_evidence(
            consultant_id=base_scope.consultant_id,
            client_id=base_scope.client_id,
            project_id=base_scope.project_id,
            process_id=base_scope.process_id,
            process_name=base_scope.process_name,
            entities=entities,
            relationships=rel_dicts,
            claims=claim_dicts,
            gaps=gap_dicts,
            contradictions=contra_dicts,
            impacts=impact_dicts,
            source_text=raw_content,
            source_title=source_title,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "canonical mirror: write_evidence fallito per %s (%s)", workspace_project_id, exc
        )
        return {"mirrored": False, "reason": str(exc), "scope": scope_out}

    return {"mirrored": True, "scope": scope_out, "counts": counts}
