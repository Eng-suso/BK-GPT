"""Clienti, progetti e processi possono chiudersi senza sparire.

Revision ID: 0005_workspace_archive
Revises: 0004_project_objective
Create Date: 2026-09-07

Il workspace conosceva solo record attivi. Un cliente chiuso, un progetto finito
o un processo dismesso restavano nell'elenco del lavoro corrente come tutti gli
altri, e l'unica alternativa era cancellarli - cioe' perdere l'incarico, le sue
decisioni e le sue fonti. `archived_at` distingue "non lo sto piu' seguendo" da
"non e' mai esistito": il record esce dagli elenchi operativi e resta leggibile
in archivio, con il motivo per cui e' stato chiuso.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_workspace_archive"
down_revision = "0004_project_objective"
branch_labels = None
depends_on = None

_TABLES = ("workspace_clients", "workspace_projects", "workspace_processes")
_COLUMNS = ("archived_at", "archive_reason")


def _columns(bind, table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    """Aggiunge lo stato di archiviazione a clienti, progetti e processi."""
    bind = op.get_bind()

    for table in _TABLES:
        existing = _columns(bind, table)

        if "archived_at" not in existing:
            op.add_column(table, sa.Column("archived_at", sa.String(), nullable=True))
            op.create_index(f"ix_{table}_archived_at", table, ["archived_at"])

        if "archive_reason" not in existing:
            op.add_column(table, sa.Column("archive_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    """Toglie lo stato di archiviazione."""
    bind = op.get_bind()

    for table in _TABLES:
        existing = _columns(bind, table)

        if "archived_at" in existing:
            op.drop_index(f"ix_{table}_archived_at", table_name=table)
            op.drop_column(table, "archived_at")

        if "archive_reason" in existing:
            op.drop_column(table, "archive_reason")
