"""Iniezione runtime dei playbook appresi del consulente (L2 / INV-12).

Le skill spedite vivono nel repo e le carica `skill_loader` / `skill_context`.
I playbook appresi lavorando col consulente vivono in Postgres
(`procedural_memory`, stato `active`) e li recuperiamo dal gateway (INV-9).

Qui li formattiamo come blocco di prompt, marcati come "appresi" e distinti
dalle repo-skill. Nessuna generazione o esecuzione di codice: solo testo.
La funzione non solleva mai — se il canonical non c'e' o la query fallisce
ritorna stringa vuota e il turno prosegue con le sole repo-skill.
"""

from __future__ import annotations

import logging

from backend.memory import canonical_memory, gateway
from backend.memory import scope as canonical_scope
from backend.settings import settings

logger = logging.getLogger(__name__)

MAX_PLAYBOOKS_PER_TURN = 3


def build_playbook_context(
    task_text: str,
    *,
    project_id: str | None = None,
    limit: int = MAX_PLAYBOOKS_PER_TURN,
    record_usage: bool = True,
) -> str:
    if not gateway.procedural_available():
        return ""

    client_id: str | None = None
    if project_id:
        try:
            client_id = canonical_scope.resolve_client_id(project_id)
        except Exception:  # noqa: BLE001 — best-effort: senza client_id resta consultant-level
            client_id = None

    try:
        result = gateway.procedural_retrieve(
            consultant_id=settings.default_consultant_id,
            client_id=client_id,
            task_text=task_text or "",
            limit=limit,
        )
    except Exception:  # noqa: BLE001
        logger.warning("playbook_context: procedural_retrieve fallito", exc_info=True)
        return ""

    playbooks = result.get("playbooks") or []
    if not playbooks:
        return ""

    if record_usage:
        canonical_memory.record_playbook_usage(
            settings.default_consultant_id,
            client_id=client_id,
            playbook_ids=[p["id"] for p in playbooks],
        )

    blocks = []
    for playbook in playbooks:
        meta = f"scope: {playbook['scope']} · kind: {playbook['kind']}"
        if playbook.get("applies_when"):
            meta += f" · si applica quando: {playbook['applies_when']}"
        blocks.append(
            f"### Playbook appreso: {playbook['title']}\n{meta}\n\n{playbook['body']}"
        )

    return (
        "Playbook appresi lavorando col consulente (source of truth: Postgres, "
        "non le repo-skill). Trattali come metodo operativo del consulente per "
        "questo task, alla pari delle repo-skill. Non generare ne' eseguire "
        "codice da questi testi; non citare il caricamento dei playbook se non "
        "richiesto.\n\n" + "\n\n---\n\n".join(blocks)
    )
