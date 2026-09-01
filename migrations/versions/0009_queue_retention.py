"""delir_worker puo' potare le code (retention) + requeue dei bloccati

Revision ID: 0009_queue_retention
Revises: 0008_dedup_partial_indexes
Create Date: 2026-09-01

Le due code (`graph_outbox`, `mem0_projection_log`) sono materializzate e
ricostruibili (INV-2): tenere le righe gia' processate all'infinito non serve.
Il worker (delir_worker) ora puo' cancellare le proprie righe processate.

Il requeue dei payload bloccati (`attempts >= 5`) resta un'azione esplicita di
`scripts/queue_admin.py` come delir_migrator: un dead-letter non si ripulisce
da solo.
"""

from __future__ import annotations

from alembic import op

revision = "0009_queue_retention"
down_revision = "0008_dedup_partial_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("GRANT DELETE ON graph_outbox, mem0_projection_log TO delir_worker;")


def downgrade() -> None:
    op.execute("REVOKE DELETE ON graph_outbox, mem0_projection_log FROM delir_worker;")
