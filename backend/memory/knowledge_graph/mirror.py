"""Specchia l'evidenza estratta dai toolset (project_memory / process_memory)
sul canonical, oltre al vecchio knowledge_graph_store.

Best-effort e non bloccante: se il canonical non e' configurato, o lo scope
non si risolve, o una singola scrittura fallisce, si registra e si va avanti.
Il chiamante non deve mai fallire per colpa di questo modulo.

E' uno strato transitorio (slice 3 del piano "Cervello DeliR"): quando il
rewire sara' completo il vecchio store sparira' e questo modulo former`a`
l'unico percorso di scrittura, chiamato direttamente invece che "in specchio".

Le forme attese per relationships/claims/gaps/contradictions/impacts sono le
stesse dei modelli in backend.toolsets.{project,process}_memory /
backend.memory.knowledge_graph.models (duck-typing sugli attributi).
"""

from __future__ import annotations

import logging
from typing import Any

from backend.memory import scope as scope_module
from backend.memory.knowledge_graph import canonical
from backend.memory.scope import ScopeIds
from backend.settings import settings

logger = logging.getLogger(__name__)

_CONFIDENCE_WORDS = {"low": 0.3, "medium": 0.6, "high": 0.9, "unknown": 0.5}


def enabled() -> bool:
    return bool(settings.canonical_database_url and settings.canonical_ingest_mirror)


def _as_confidence(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return _CONFIDENCE_WORDS.get(str(value or "").lower(), 0.5)


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
) -> dict[str, Any]:
    if not enabled():
        return {"mirrored": False, "reason": "disabled"}

    process_ids = [p for p in (workspace_process_ids or []) if p]
    process_scope: dict[str, ScopeIds] = {}

    try:
        base_scope = scope_module.resolve(workspace_project_id, process_ids[0] if process_ids else None)
        if process_ids:
            process_scope[process_ids[0]] = base_scope
        for wpid in process_ids[1:]:
            process_scope[wpid] = scope_module.resolve(workspace_project_id, wpid)
    except Exception as exc:  # noqa: BLE001
        logger.warning("canonical mirror: scope non risolvibile per %s (%s)", workspace_project_id, exc)
        return {"mirrored": False, "reason": str(exc)}

    def _canonical_process_ids(workspace_ids: list[str] | None) -> list[str]:
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

    entity_ids: dict[str, str] = {}
    counts = {"entities": 0, "relationships": 0, "claims": 0, "gaps": 0, "contradictions": 0, "impacts": 0}
    errors: list[str] = []

    def _entity(name: str) -> str:
        cleaned = " ".join(str(name or "").split())
        if not cleaned:
            return ""
        if cleaned not in entity_ids:
            try:
                entity_ids[cleaned] = canonical.write_entity(
                    base_scope.consultant_id, base_scope.client_id, "other", cleaned,
                    project_id=base_scope.project_id, process_id=base_scope.process_id,
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"entity {cleaned!r}: {exc}")
                return ""
        return entity_ids[cleaned]

    for name in entities or []:
        if _entity(name):
            counts["entities"] += 1

    for rel in relationships or []:
        try:
            src, tgt = _entity(rel.source), _entity(rel.target)
            if not src or not tgt:
                continue
            canonical.write_relation(
                base_scope.consultant_id, base_scope.client_id, src, rel.relation, tgt,
                project_id=base_scope.project_id, process_id=base_scope.process_id,
                evidence=rel.evidence, confidence=_as_confidence(rel.confidence),
                confirmed=bool(rel.confirmed),
            )
            counts["relationships"] += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"relationship {rel!r}: {exc}")

    for claim in claims or []:
        try:
            canonical.write_claim(
                base_scope.consultant_id, base_scope.client_id, claim.claim, claim.process_area,
                project_id=base_scope.project_id, process_id=base_scope.process_id,
                claim_status=claim.status, linked_element_hint=claim.linked_element_hint,
                confidence=_as_confidence(claim.confidence),
            )
            counts["claims"] += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"claim {claim!r}: {exc}")

    for gap in gaps or []:
        try:
            canonical.write_gap(
                base_scope.consultant_id, base_scope.client_id, gap.title, gap.missing_information,
                project_id=base_scope.project_id, process_id=base_scope.process_id,
                required_evidence=gap.required_evidence, severity=gap.severity,
                affected_process_ids=_canonical_process_ids(gap.affected_process_ids),
            )
            counts["gaps"] += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"gap {gap!r}: {exc}")

    for contra in contradictions or []:
        try:
            canonical.write_contradiction(
                base_scope.consultant_id, base_scope.client_id, contra.title,
                project_id=base_scope.project_id, process_id=base_scope.process_id,
                conflicting_statements=list(contra.conflicting_claims),
                resolution_question=contra.resolution_question, severity=contra.severity,
                affected_process_ids=_canonical_process_ids(contra.affected_process_ids),
            )
            counts["contradictions"] += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"contradiction {contra!r}: {exc}")

    for impact in impacts or []:
        try:
            canonical.write_impact(
                base_scope.consultant_id, base_scope.client_id, impact.title,
                impact.impact_area, impact.mechanism,
                project_id=base_scope.project_id, process_id=base_scope.process_id,
                evidence=impact.evidence,
                affected_process_ids=_canonical_process_ids(impact.affected_process_ids),
                confidence=_as_confidence(impact.confidence),
            )
            counts["impacts"] += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"impact {impact!r}: {exc}")

    if errors:
        logger.warning("canonical mirror: %d errori su %s", len(errors), workspace_project_id)

    return {
        "mirrored": True,
        "scope": {
            "consultant_id": base_scope.consultant_id,
            "client_id": base_scope.client_id,
            "project_id": base_scope.project_id,
            "process_id": base_scope.process_id,
        },
        "counts": counts,
        "errors": errors,
    }
