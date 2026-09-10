"""Un piano sa su quali fonti e' stato costruito.

Revision ID: 0008_review_evidence_source_set
Revises: 0007_episode_process_scope
Create Date: 2026-09-09

La review e' il piano del processo, ma non dichiarava da quale evidenza fosse
nata. Senza quel dato "il piano e' aggiornato rispetto alle interviste?" non era
una domanda a cui si potesse rispondere: una quarta intervista entrava agli atti
e il piano restava quello di prima, indistinguibile da un piano appena
sintetizzato. Il Canvas leggeva quel piano e disegnava un AS-IS che ignorava una
fonte, senza che nessuno potesse accorgersene.

La colonna tiene il `source_set_id` del registro dell'evidenza al momento della
preparazione. Le review gia' salvate restano NULL: significa "non si sa su cosa
sia stata costruita", che e' diverso da "costruita su nessuna fonte", e il
runtime la tratta come da risintetizzare quando l'evidenza esiste.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_review_evidence_source_set"
down_revision = "0007_episode_process_scope"
branch_labels = None
depends_on = None

_COLUMN = "evidence_source_set_id"
_TABLES = ("workspace_bpmn_reviews", "workspace_bpmn_review_versions")


def _columns(bind, table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    for table in _TABLES:
        if _COLUMN not in _columns(bind, table):
            op.add_column(table, sa.Column(_COLUMN, sa.String(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    for table in _TABLES:
        if _COLUMN in _columns(bind, table):
            op.drop_column(table, _COLUMN)
