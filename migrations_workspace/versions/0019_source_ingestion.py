"""Conserva file e dimensioni indipendenti delle fonti.

Revision ID: 0019_source_ingestion
Revises: 0018_merge_notification_reads

`content_hash` esiste gia' (0015_source_content_hash, l'impronta del testo):
qui riceve l'indice, perche' un file caricato si ritrova per hash nel progetto.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0019_source_ingestion"
down_revision = "0018_merge_notification_reads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("workspace_sources")}
    additions = (
        ("roles_json", sa.Text(), False, "[]"),
        ("retention", sa.String(), False, "persistent"),
        ("scopes_json", sa.Text(), False, "[]"),
        ("status", sa.String(), False, "reference"),
        ("byte_size", sa.Integer(), True, None),
        ("mime_type", sa.String(), True, None),
        ("storage_key", sa.String(), True, None),
        ("extracted_text", sa.Text(), True, None),
        ("parser", sa.String(), True, None),
        ("ingestion_key", sa.String(), True, None),
    )
    for name, kind, nullable, default in additions:
        if name not in columns:
            op.add_column(
                "workspace_sources",
                sa.Column(name, kind, nullable=nullable, server_default=default),
            )
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("workspace_sources")}
    if "ix_workspace_sources_content_hash" not in indexes:
        op.create_index(
            "ix_workspace_sources_content_hash", "workspace_sources", ["content_hash"]
        )
    constraints = {
        item["name"] for item in sa.inspect(bind).get_unique_constraints("workspace_sources")
    }
    if "uq_workspace_source_ingestion" not in constraints:
        op.create_unique_constraint(
            "uq_workspace_source_ingestion",
            "workspace_sources",
            ["tenant_id", "project_id", "ingestion_key"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("workspace_sources")}
    constraints = {
        item["name"] for item in sa.inspect(bind).get_unique_constraints("workspace_sources")
    }
    if "uq_workspace_source_ingestion" in constraints:
        op.drop_constraint(
            "uq_workspace_source_ingestion", "workspace_sources", type_="unique"
        )
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("workspace_sources")}
    if "ix_workspace_sources_content_hash" in indexes:
        # Solo l'indice: la colonna e' di 0015_source_content_hash.
        op.drop_index("ix_workspace_sources_content_hash", table_name="workspace_sources")
    for name in reversed(
        [
            "roles_json",
            "retention",
            "scopes_json",
            "status",
            "byte_size",
            "mime_type",
            "storage_key",
            "extracted_text",
            "parser",
            "ingestion_key",
        ]
    ):
        if name in columns:
            op.drop_column("workspace_sources", name)
