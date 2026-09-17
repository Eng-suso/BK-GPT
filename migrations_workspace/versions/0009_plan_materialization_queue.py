"""Il piano si ricostruisce quando cambia l'evidenza, non quando si preme il bottone.

Revision ID: 0009_plan_materialization_queue
Revises: 0008_review_evidence_source_set
Create Date: 2026-09-13

La sintesi del piano - tre chiamate al modello - viveva dentro il percorso
critico di «Genera BPMN». Il lavoro appartiene al momento in cui la conoscenza
cambia: una fonte salvata mette in coda il processo, un worker ricostruisce il
piano, e quando il consulente chiede il disegno il piano c'e' gia'.

Una riga per processo: cinque interviste salvate di seguito sono una sintesi
dopo l'ultima, non cinque sintesi. `requested_at` si sposta in avanti a ogni
richiesta, `next_attempt_at` regge il backoff dei tentativi falliti.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009_plan_materialization_queue"
down_revision = "0008_review_evidence_source_set"
branch_labels = None
depends_on = None

_TABLE = "workspace_plan_materializations"


def _has_table(bind, table: str) -> bool:
    return sa.inspect(bind).has_table(table)


def upgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, _TABLE):
        return

    op.create_table(
        _TABLE,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(), nullable=False, server_default="local"),
        sa.Column("process_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("requested_at", sa.String(), nullable=False),
        sa.Column("reason", sa.String(), nullable=False, server_default=""),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.String(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.String(), nullable=True),
        sa.Column("last_action", sa.String(), nullable=True),
        sa.Column("plan_version", sa.Integer(), nullable=True),
        sa.UniqueConstraint("tenant_id", "process_id", name="uq_plan_materialization_process"),
    )
    op.create_index(
        "ix_plan_materialization_ready",
        _TABLE,
        ["status", "next_attempt_at"],
    )
    op.create_index("ix_plan_materialization_tenant", _TABLE, ["tenant_id"])
    op.create_index("ix_plan_materialization_process", _TABLE, ["process_id"])


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind, _TABLE):
        return
    op.drop_index("ix_plan_materialization_process", table_name=_TABLE)
    op.drop_index("ix_plan_materialization_tenant", table_name=_TABLE)
    op.drop_index("ix_plan_materialization_ready", table_name=_TABLE)
    op.drop_table(_TABLE)
