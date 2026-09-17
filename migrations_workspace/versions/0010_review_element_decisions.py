"""Le decisioni del consulente sugli elementi che nessuna fonte regge.

Revision ID: 0010_review_element_decisions
Revises: 0009_plan_materialization_queue
Create Date: 2026-09-17

Il rapporto di provenance dice quali elementi del piano sono un'inferenza. Chi
conosce il processo li rivede: ne conferma alcuni - "si', succede cosi', solo
che nessuno l'ha detto nelle interviste" - e ne rifiuta altri. Quella decisione
e' conoscenza umana: si tiene sulla review, per riferimento di tracciabilita',
separata da cio' che il modello ha estratto, come le risposte alle domande.

Le review gia' salvate partono da `{}`: nessuna decisione presa.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_review_element_decisions"
down_revision = "0009_plan_materialization_queue"
branch_labels = None
depends_on = None

_TABLE = "workspace_bpmn_reviews"
_COLUMN = "element_decisions_json"


def _columns(bind) -> set[str]:
    return {column["name"] for column in sa.inspect(bind).get_columns(_TABLE)}


def upgrade() -> None:
    bind = op.get_bind()
    if _COLUMN not in _columns(bind):
        op.add_column(
            _TABLE,
            sa.Column(_COLUMN, sa.Text(), nullable=False, server_default="{}"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _COLUMN in _columns(bind):
        op.drop_column(_TABLE, _COLUMN)
