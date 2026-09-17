"""L'ultima verifica di conformita' fra canvas, piano e fonti.

Revision ID: 0011_review_conformance
Revises: 0010_review_element_decisions
Create Date: 2026-09-17

Ogni bozza BPMN passa da un revisore che confronta il canvas salvato con il
piano e il piano con le fonti intere. L'esito - verdetto, rilievi con le
citazioni verificate, lo snapshot e l'impronta del canvas su cui e' stato fatto -
si tiene sulla review, cosi' la UI e chi riapre il processo possono leggere se
il disegno che vedono e' stato verificato, e su quale versione.

Le review gia' salvate partono da NULL: mai verificate.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011_review_conformance"
down_revision = "0010_review_element_decisions"
branch_labels = None
depends_on = None

_TABLE = "workspace_bpmn_reviews"
_COLUMN = "conformance_json"


def _columns(bind) -> set[str]:
    return {column["name"] for column in sa.inspect(bind).get_columns(_TABLE)}


def upgrade() -> None:
    bind = op.get_bind()
    if _COLUMN not in _columns(bind):
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if _COLUMN in _columns(bind):
        op.drop_column(_TABLE, _COLUMN)
