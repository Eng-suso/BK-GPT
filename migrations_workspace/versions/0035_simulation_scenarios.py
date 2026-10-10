"""Gli scenari del workspace AS-IS | A | B | C (SIM-14).

Revision ID: 0035_simulation_scenarios
Revises: 0034_simulation_run_queue
Create Date: 2026-10-10

Finora lo scenario era una sola bozza nel browser del consulente: un secondo
scenario sovrascriveva il primo e il confronto si faceva fra run sparsi. Ora
ogni processo ha un AS-IS (la bozza intera e il seed comune) e fino a cinque
alternative, ognuna come patch sull'AS-IS.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0035_simulation_scenarios"
down_revision = "0034_simulation_run_queue"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0001 usa i metadati ORM correnti su un database nuovo, tabella compresa.
    if sa.inspect(op.get_bind()).has_table("workspace_simulation_scenarios"):
        return
    op.create_table(
        "workspace_simulation_scenarios",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(), nullable=False, server_default="local"),
        sa.Column("bpmn_model_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("draft_json", sa.Text(), nullable=True),
        sa.Column("patch_json", sa.Text(), nullable=True),
        sa.Column("seed", sa.Integer(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.UniqueConstraint("tenant_id", "bpmn_model_id", "label", name="uq_simulation_scenario_label"),
    )
    op.create_index("ix_workspace_simulation_scenarios_tenant_id", "workspace_simulation_scenarios", ["tenant_id"])
    op.create_index("ix_workspace_simulation_scenarios_bpmn_model_id", "workspace_simulation_scenarios", ["bpmn_model_id"])


def downgrade() -> None:
    op.drop_table("workspace_simulation_scenarios")
