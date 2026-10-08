"""Il CSV di eventi di ogni run di simulazione, per poterlo esportare.

Revision ID: 0030_simulation_run_logs
Revises: 0029_impact_review_actions
Create Date: 2026-10-07

SIM-06: il log del motore finora si leggeva e si buttava. Ora si tiene, in una
tabella a parte dall'artefatto, e da li' si esporta come event log canonico.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0030_simulation_run_logs"
down_revision = "0029_impact_review_actions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0001 usa i metadati ORM correnti su un database nuovo, tabella compresa.
    if sa.inspect(op.get_bind()).has_table("workspace_simulation_run_logs"):
        return
    op.create_table(
        "workspace_simulation_run_logs",
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("workspace_simulation_runs.id"), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False, server_default="local"),
        sa.Column("log_csv", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
    )
    op.create_index("ix_workspace_simulation_run_logs_tenant_id", "workspace_simulation_run_logs", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("workspace_simulation_run_logs")
