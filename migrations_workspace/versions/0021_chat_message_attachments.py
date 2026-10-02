"""Un messaggio della chat ricorda gli allegati con cui e' partito.

Revision ID: 0021_chat_message_attachments
Revises: 0020_source_acquisition
Create Date: 2026-10-02

Prima il messaggio salvava solo il testo: un file caricato dal composer partiva
con il turno, ma nella conversazione non ne restava traccia, ne' subito ne'
ricaricando. Qui si conserva cosa e' stato allegato - tipo, id, etichetta -
quanto basta per mostrarlo; il contenuto resta nella fonte.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0021_chat_message_attachments"
down_revision = "0020_source_acquisition"
branch_labels = None
depends_on = None

_TABLE = "chat_messages"
_COLUMN = "attachments_json"


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
