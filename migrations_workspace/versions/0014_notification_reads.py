"""Quali avvisi il consulente ha gia' letto.

Revision ID: 0014_notification_reads
Revises: 0013_conformance_lease
Create Date: 2026-09-20

Gli avvisi non sono un registro di eventi a parte: si leggono dai fatti che il
workspace gia' conserva - un piano ricostruito, un confronto con le fonti che ha
trovato qualcosa, una simulazione finita. Scriverli una seconda volta in una
tabella di eventi significherebbe due verita' che possono divergere, e la
seconda sarebbe quella sbagliata.

Cio' che i fatti non sanno e' se qualcuno li ha gia' visti. Quella e' l'unica
cosa che si registra qui: l'id stabile dell'avviso e quando e' stato letto.
Una riga per avviso e per tenant, cosi' "non letti" e' un conteggio vero e non
un badge fisso.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014_notification_reads"
down_revision = "0013_conformance_lease"
branch_labels = None
depends_on = None

_TABLE = "workspace_notification_reads"


def _tables(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    if _TABLE in _tables(bind):
        return

    op.create_table(
        _TABLE,
        sa.Column("tenant_id", sa.String(), nullable=False),
        # L'id e' derivato dal fatto (`conformance:<modello>:<data>`): un avviso
        # che descrive uno stato nuovo e' un avviso nuovo, e torna non letto.
        sa.Column("notification_id", sa.String(), nullable=False),
        sa.Column("read_at", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "notification_id"),
    )
    op.create_index(
        "workspace_notification_reads_tenant",
        _TABLE,
        ["tenant_id"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    if _TABLE not in _tables(bind):
        return
    op.drop_index("workspace_notification_reads_tenant", table_name=_TABLE)
    op.drop_table(_TABLE)
