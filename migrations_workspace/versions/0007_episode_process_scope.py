"""Un episodio sa a quale processo appartiene.

Revision ID: 0007_episode_process_scope
Revises: 0006_project_lead_and_dates
Create Date: 2026-09-08

L'appartenenza di un'intervista a un processo viveva dentro `tags`, come la
stringa "process:<id>", e il filtro era una ricerca testuale: "process:proc-1"
faceva match anche su "process:proc-10", e bastava che quel testo comparisse in
una sintesi per far passare l'episodio sbagliato. Una colonna rende
l'appartenenza una condizione, non una coincidenza di caratteri.

Il tag resta scritto per compatibilita' con gli episodi gia' salvati; la
colonna viene popolata da quelli, quando il tag c'e'.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007_episode_process_scope"
down_revision = "0006_project_lead_and_dates"
branch_labels = None
depends_on = None

_TABLE = "episodes"
_COLUMN = "process_id"
_INDEX = "ix_episodes_project_process"


def _columns(bind) -> set[str]:
    return {column["name"] for column in sa.inspect(bind).get_columns(_TABLE)}


def upgrade() -> None:
    """Aggiunge la colonna e la deriva dal tag `process:<id>` gia' salvato."""
    bind = op.get_bind()
    if _COLUMN in _columns(bind):
        return

    op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(), nullable=True))
    # `tags` e' un array JSON di stringhe: si estrae il primo "process:<id>".
    op.execute(
        "UPDATE episodes "
        "SET process_id = substring(tags from 'process:([^\"]+)') "
        "WHERE tags LIKE '%process:%'"
    )
    op.create_index(_INDEX, _TABLE, ["project", _COLUMN])


def downgrade() -> None:
    """Torna al solo tag."""
    bind = op.get_bind()
    if _COLUMN not in _columns(bind):
        return

    op.drop_index(_INDEX, table_name=_TABLE)
    op.drop_column(_TABLE, _COLUMN)
