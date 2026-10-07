"""`workspace_read`: lo snapshot operativo della workspace, scoped (INV-9)."""

from __future__ import annotations

from typing import Any

# --------------------------------------------------------------------------- #
# workspace_read — snapshot operativo della workspace, scoped (INV-9)
# --------------------------------------------------------------------------- #

_WS_SECTIONS = ("processes", "sources", "decisions")


def workspace_read(
    *,
    project_id: str,
    process_ids: list[str] | None = None,
    include: tuple[str, ...] = _WS_SECTIONS,
) -> dict[str, Any]:
    """Snapshot operativo scoped della workspace (Postgres, SoT operativa INV-8).

    Unico read che i tool di retrieval usano per il grounding operativo.
    `process_ids` filtra i processi + le sources/decisions collegate; quelle
    project-level (senza `process_id`) restano sempre. Project inesistente ->
    status `not_found`, nessuna eccezione.
    """
    from backend import workspace_database
    from backend.agents.scope_guard import assert_project_in_scope

    # G3: dentro un agent run il project_id deve essere quello autorizzato per il
    # thread, non uno scelto dall'LLM. No-op fuori da un run (worker/test).
    assert_project_in_scope(project_id)

    project = workspace_database.get_project(project_id)
    if project is None:
        return {"status": "not_found", "project": None}

    wanted = {str(p) for p in (process_ids or []) if p}
    out: dict[str, Any] = {"status": "ok", "project": project}

    if "processes" in include:
        procs = workspace_database.list_project_processes(project_id)
        out["processes"] = [p for p in procs if p.get("id") in wanted] if wanted else procs

    def _scoped(rows: list[dict]) -> list[dict]:
        if not wanted:
            return rows
        return [r for r in rows if not r.get("process_id") or r.get("process_id") in wanted]

    if "sources" in include:
        out["sources"] = _scoped(workspace_database.list_project_sources(project_id))
    if "decisions" in include:
        out["decisions"] = _scoped(workspace_database.list_project_decisions(project_id))

    return out
