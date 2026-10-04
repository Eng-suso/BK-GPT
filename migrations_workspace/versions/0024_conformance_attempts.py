"""Il confronto con le fonti conta i suoi tentativi.

Revision ID: 0024_conformance_attempts
Revises: 0023_source_graph
Create Date: 2026-10-03

Un confronto che fallisce sempre (provider giu', fonte che fa cadere il
revisore) veniva ripreso a ogni scadenza della presa in carico, per sempre.
Con il conto dei tentativi la coda smette dopo un tetto e lo dice
(`conformance_status = 'failed'`); un disegno nuovo riparte da zero.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0024_conformance_attempts"
down_revision = "0023_source_graph"
branch_labels = None
depends_on = None

_REVIEWS = "workspace_bpmn_reviews"


def upgrade() -> None:
    # La revision di base crea le tabelle dai modelli (`create_all`): su un
    # database nuovo la colonna c'e' gia', come per le colonne della 0022/0023.
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns(_REVIEWS)}
    if "conformance_attempts" not in columns:
        op.add_column(
            _REVIEWS,
            sa.Column("conformance_attempts", sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    op.drop_column(_REVIEWS, "conformance_attempts")
