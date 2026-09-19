"""Lo stato del confronto con le fonti: in attesa, in corso, fatto.

Revision ID: 0012_review_conformance_status
Revises: 0011_review_conformance
Create Date: 2026-09-17

Il confronto non sta piu' dentro la generazione: il disegno esce in pochi
secondi e la verifica gira dopo, cosi' il consulente itera invece di aspettare
minuti. Serve quindi sapere, per ogni processo, se un confronto e' in attesa:
e' una colonna e non un campo del JSON accanto perche' il worker la interroga.

Le review gia' salvate partono da NULL: nessun confronto in coda.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_review_conformance_status"
down_revision = "0011_review_conformance"
branch_labels = None
depends_on = None

_TABLE = "workspace_bpmn_reviews"
_COLUMN = "conformance_status"


def _columns(bind) -> set[str]:
    return {column["name"] for column in sa.inspect(bind).get_columns(_TABLE)}


def upgrade() -> None:
    bind = op.get_bind()
    if _COLUMN not in _columns(bind):
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(), nullable=True))
        op.create_index(f"ix_{_TABLE}_{_COLUMN}", _TABLE, [_COLUMN])


def downgrade() -> None:
    bind = op.get_bind()
    if _COLUMN in _columns(bind):
        op.drop_index(f"ix_{_TABLE}_{_COLUMN}", table_name=_TABLE)
        op.drop_column(_TABLE, _COLUMN)
