"""Un incarico ha un referente e una finestra temporale.

Revision ID: 0006_project_lead_and_dates
Revises: 0005_workspace_archive
Create Date: 2026-09-08

Il progetto sapeva in che fase era e quanto era avanti, ma non chi lo segue ne'
fra quali date sta. Il referente mostrato nell'elenco era preso in prestito dal
primo processo registrato: un progetto senza processi non aveva referente, e uno
con tre processi ne mostrava uno a caso. Le date non esistevano affatto, quindi
"in ritardo" era un giudizio che il consulente doveva tenere a mente.

Tre colonne facoltative: un incarico gia' registrato resta valido senza, e i
placeholder li mette `workspace_defaults` come per gli altri campi.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_project_lead_and_dates"
down_revision = "0005_workspace_archive"
branch_labels = None
depends_on = None

_TABLE = "workspace_projects"
_COLUMNS = {
    "lead": sa.Column("lead", sa.String(), nullable=True),
    "start_date": sa.Column("start_date", sa.String(), nullable=True),
    "end_date": sa.Column("end_date", sa.String(), nullable=True),
}


def _existing(bind) -> set[str]:
    return {column["name"] for column in sa.inspect(bind).get_columns(_TABLE)}


def upgrade() -> None:
    """Aggiunge referente, data di inizio e data di fine al progetto."""
    existing = _existing(op.get_bind())

    for name, column in _COLUMNS.items():
        if name not in existing:
            op.add_column(_TABLE, column)


def downgrade() -> None:
    """Toglie referente e date.

    Perde i valori registrati: sono dati dichiarati dal consulente e non
    ricostruibili da altre colonne. Non ci sono indici ne' vincoli da rimuovere.
    """
    existing = _existing(op.get_bind())

    for name in _COLUMNS:
        if name in existing:
            op.drop_column(_TABLE, name)
