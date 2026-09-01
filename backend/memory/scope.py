"""Ponte tra gli id stringa del workspace e le righe canonical.

Finche' `workspace.db` (SQLite) non e' migrato su Postgres, l'ingestion mappa
"project-1" / "proc-1" a `client` / `project` / `process` canonical (uuid) con
un upsert idempotente su `workspace_id` (migration 0007).

Consulente = quello unico di default (`settings.default_consultant_id`).
Cliente = derivato dal campo `client` del progetto workspace.

Se il canonical non e' configurato o il workspace non conosce l'id, `resolve`
solleva: i chiamanti (best-effort mirror) la catturano.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import text

from backend import workspace_database
from backend.db import canonical_session
from backend.settings import settings


@dataclass(frozen=True)
class ScopeIds:
    consultant_id: str
    client_id: str
    project_id: str
    process_id: str | None
    process_name: str | None = None


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-") or "sconosciuto"


def _upsert(session, table: str, workspace_id: str, name: str, extra_cols: dict) -> str:
    cols = ["workspace_id", "name", *extra_cols]
    placeholders = ", ".join(f":{c}" for c in cols)
    params = {"workspace_id": workspace_id, "name": name, **extra_cols}
    row = session.execute(
        text(
            f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT (workspace_id) WHERE workspace_id IS NOT NULL "
            f"DO UPDATE SET name = EXCLUDED.name "
            f"RETURNING id"
        ),
        params,
    ).one()
    return str(row.id)


def resolve_client_id(workspace_project_id: str) -> str | None:
    """Solo lettura: workspace project id -> `client_id` canonical.

    `None` se il canonical non e' configurato, o il progetto / cliente non
    sono ancora stati materializzati. Non crea righe (a differenza di
    `resolve`): serve ai path di lettura (recall Mem0 client-scoped).
    """
    if not settings.canonical_database_url:
        return None
    try:
        project = workspace_database.get_project(workspace_project_id)
        if project is None:
            return None
        client_ws = f"client:{_slug(str(project.get('client') or 'Cliente'))}"
        with canonical_session(settings.default_consultant_id) as session:
            row = session.execute(
                text("SELECT id FROM client WHERE workspace_id = :w"),
                {"w": client_ws},
            ).first()
        return str(row.id) if row else None
    except Exception:  # noqa: BLE001 — la lettura non deve far fallire il chiamante
        return None


def resolve(workspace_project_id: str, workspace_process_id: str | None = None) -> ScopeIds:
    if not settings.canonical_database_url:
        raise RuntimeError("canonical_database_url non configurata")

    project = workspace_database.get_project(workspace_project_id)
    if project is None:
        raise RuntimeError(f"progetto workspace sconosciuto: {workspace_project_id}")

    consultant_id = settings.default_consultant_id
    client_name = str(project.get("client") or "Cliente")
    client_ws = f"client:{_slug(client_name)}"

    process_name = None
    if workspace_process_id:
        process = workspace_database.get_process(workspace_process_id)
        if process is not None:
            process_name = str(process.get("name") or workspace_process_id)

    # tutti gli upsert in un unico contesto consultant-only: la policy
    # strict-client permette la scrittura quando app_client_id() IS NULL.
    with canonical_session(consultant_id) as session:
        client_id = _upsert(
            session, "client", client_ws, client_name,
            {"consultant_id": consultant_id},
        )
        project_id = _upsert(
            session, "project", workspace_project_id,
            str(project.get("name") or workspace_project_id),
            {"consultant_id": consultant_id, "client_id": client_id},
        )
        process_id = None
        if workspace_process_id:
            process_id = _upsert(
                session, "process", workspace_process_id,
                process_name or workspace_process_id,
                {
                    "consultant_id": consultant_id,
                    "client_id": client_id,
                    "project_id": project_id,
                },
            )

    return ScopeIds(consultant_id, client_id, project_id, process_id, process_name)
