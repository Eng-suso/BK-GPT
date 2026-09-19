"""Quando un confronto e' stato preso in carico: una presa in carico scade.

Revision ID: 0013_conformance_lease
Revises: 0012_review_conformance_status
Create Date: 2026-09-18

La coda dei confronti marcava `running` e basta. Se il processo che stava
lavorando muore - un riavvio, un deploy, un crash a meta' della lettura delle
fonti, che dura minuti - quella riga non torna eleggibile da sola: nessuno la
rilavora piu' e il pannello del consulente mostra "Confronto in corso" per
sempre, che e' il peggiore dei tre stati perche' sembra lavoro in corso.

E' lo stesso difetto che la coda dei piani aveva gia' risolto con una scadenza
(`MATERIALIZATION_LEASE_SECONDS`), e che il commento di quella coda dichiara:
un lease che nessuno rilascia e' il modo in cui una coda si blocca in silenzio.

Le review gia' salvate partono da NULL: nessuna presa in carico in corso.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013_conformance_lease"
down_revision = "0012_review_conformance_status"
branch_labels = None
depends_on = None

_TABLE = "workspace_bpmn_reviews"
_COLUMN = "conformance_leased_at"


def _columns(bind) -> set[str]:
    return {column["name"] for column in sa.inspect(bind).get_columns(_TABLE)}


def upgrade() -> None:
    bind = op.get_bind()
    if _COLUMN not in _columns(bind):
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if _COLUMN in _columns(bind):
        op.drop_column(_TABLE, _COLUMN)
