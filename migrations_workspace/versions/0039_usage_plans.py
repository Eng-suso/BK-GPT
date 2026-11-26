"""Il piano d'uso dei consulenti in prova.

Revision ID: 0039_usage_plans
Revises: 0038_usage_user
Create Date: 2026-11-26

Una riga per consulente: soglie (NULL = default dei settings), inizio e fine
della prova, inizio della sessione di cinque ore in corso. La spesa non si
copia qui: si legge dal registro dei consumi, che resta l'unica fonte.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0039_usage_plans"
down_revision = "0038_usage_user"
branch_labels = None
depends_on = None

_TABLE = "workspace_usage_plans"


def upgrade() -> None:
    # 0001 crea le tabelle dai metadati ORM su un database nuovo.
    if _TABLE in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        _TABLE,
        sa.Column("user_id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False, server_default="local"),
        sa.Column("session_budget_usd", sa.String(), nullable=True),
        sa.Column("week_budget_usd", sa.String(), nullable=True),
        sa.Column("trial_budget_usd", sa.String(), nullable=True),
        sa.Column("trial_started_at", sa.String(), nullable=False),
        sa.Column("trial_ends_at", sa.String(), nullable=True),
        sa.Column("session_started_at", sa.String(), nullable=True),
        sa.Column("updated_at", sa.String(), nullable=False),
    )
    op.create_index("ix_workspace_usage_plans_tenant_id", _TABLE, ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_workspace_usage_plans_tenant_id", table_name=_TABLE)
    op.drop_table(_TABLE)
