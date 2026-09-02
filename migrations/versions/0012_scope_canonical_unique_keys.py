"""Scope canonical uniqueness to tenant/client boundaries.

Revision ID: 0012_scope_canonical_unique_keys
Revises: 0011_entity_resolution_indexes
Create Date: 2026-09-02

`workspace_id` was unique globally on the canonical backbone. Operational
workspace ids are tenant-local strings, so two consultants could collide on the
same `project-1` / `proc-1` / client slug. `kg_source` had the same class of
problem: source content dedup was global per consultant, while source rows are
client-scoped and hidden by RLS.
"""

from __future__ import annotations

from alembic import op

revision = "0012_scope_canonical_unique_keys"
down_revision = "0011_entity_resolution_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("client", "project", "process"):
        op.execute(f"DROP INDEX IF EXISTS {table}_workspace_id;")
        op.execute(
            f"CREATE UNIQUE INDEX {table}_workspace_id ON {table} "
            "(consultant_id, workspace_id) WHERE workspace_id IS NOT NULL;"
        )

    op.execute(
        "ALTER TABLE kg_source DROP CONSTRAINT IF EXISTS "
        "kg_source_consultant_id_content_hash_key;"
    )
    op.execute(
        "CREATE UNIQUE INDEX kg_source_client_content_hash ON kg_source "
        "(consultant_id, client_id, content_hash) WHERE client_id IS NOT NULL;"
    )
    op.execute(
        "CREATE UNIQUE INDEX kg_source_consultant_content_hash ON kg_source "
        "(consultant_id, content_hash) WHERE client_id IS NULL;"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS kg_source_consultant_content_hash;")
    op.execute("DROP INDEX IF EXISTS kg_source_client_content_hash;")
    op.execute(
        "ALTER TABLE kg_source ADD CONSTRAINT "
        "kg_source_consultant_id_content_hash_key "
        "UNIQUE (consultant_id, content_hash);"
    )

    for table in ("client", "project", "process"):
        op.execute(f"DROP INDEX IF EXISTS {table}_workspace_id;")
        op.execute(
            f"CREATE UNIQUE INDEX {table}_workspace_id ON {table} "
            "(workspace_id) WHERE workspace_id IS NOT NULL;"
        )
