"""Il modello IR che ogni run di simulazione ha simulato.

Revision ID: 0032_simulation_run_model
Revises: 0031_merge_0030_heads
Create Date: 2026-10-08

SIM-20a: l'inspector del task deve dire cosa il run ha simulato. La richiesta
non basta: un run del contratto v2 puo' arrivare come patch sulla baseline, o
senza niente. Il modello risolto si tiene sul run; i run anteriori restano
senza (NULL) e l'inspector ripiega sulla richiesta v1.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0032_simulation_run_model"
down_revision = "0031_merge_0030_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0001 usa i metadati ORM correnti su un database nuovo, colonna compresa.
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("workspace_simulation_runs")}
    if "model_json" in columns:
        return
    op.add_column("workspace_simulation_runs", sa.Column("model_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("workspace_simulation_runs", "model_json")
