"""Bridge workspace SQLite -> canonical: workspace_id sul backbone + consulente di default

Revision ID: 0007_workspace_bridge
Revises: 0006_kg_structure
Create Date: 2026-09-01

Finche' la migrazione completa del workspace (workspace.db -> Postgres) e' una
traccia a parte, l'ingestion ha bisogno di mappare gli id stringa del workspace
("project-1", "proc-1") a righe canonical. `backend/memory/scope.py` fa
l'upsert idempotente su questi `workspace_id`.

- workspace_id text (nullable) + UNIQUE parziale su consultant/client/project/process
- seed del consulente locale di default (uuid deterministico, override via
  settings.default_consultant_id)
- UNIQUE su kg_relation per l'upsert (stessa tripla source/target/relation)
"""

from __future__ import annotations

from alembic import op

revision = "0007_workspace_bridge"
down_revision = "0006_kg_structure"
branch_labels = None
depends_on = None

_DEFAULT_CONSULTANT_ID = "3fcba7a0-4e34-59ed-9937-6879896bbdad"


def upgrade() -> None:
    for table in ("consultant", "client", "project", "process"):
        op.execute(f"ALTER TABLE {table} ADD COLUMN workspace_id text;")
        op.execute(
            f"CREATE UNIQUE INDEX {table}_workspace_id ON {table} (workspace_id) "
            f"WHERE workspace_id IS NOT NULL;"
        )

    op.execute(
        "INSERT INTO consultant (id, email, display_name, workspace_id) VALUES "
        f"('{_DEFAULT_CONSULTANT_ID}', 'local@delir.local', 'Consulente locale', 'default') "
        "ON CONFLICT (id) DO NOTHING;"
    )

    op.execute(
        "CREATE UNIQUE INDEX kg_relation_triple ON kg_relation "
        "(consultant_id, client_id, source_entity_id, target_entity_id, relation);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS kg_relation_triple;")
    op.execute(
        f"DELETE FROM consultant WHERE id = '{_DEFAULT_CONSULTANT_ID}';"
    )
    for table in ("consultant", "client", "project", "process"):
        op.execute(f"DROP INDEX IF EXISTS {table}_workspace_id;")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS workspace_id;")
