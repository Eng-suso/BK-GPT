"""Una fonte dichiara l'impronta del suo testo.

Revision ID: 0015_source_content_hash
Revises: 0014_llm_usage_ledger
Create Date: 2026-09-26

L'identita' del set di fonti (`source_set_identity`) era fatta di id, nome e
scope: diceva *quali* fonti ci sono, non *cosa dicono*. Un'intervista corretta e
risalvata con lo stesso titolo lasciava quindi l'identita' ferma, il piano
risultava "costruito sul set corrente" e nessuno lo risintetizzava: il processo
continuava a essere descritto dal testo di prima, e il difetto non aveva sintomo.

L'impronta non puo' essere calcolata al volo dal testo, perche' lo sweep dei
piani indietro (`queue_stale_process_plans`) confronta le identita' leggendo i
soli record delle fonti - senza caricare le trascrizioni, che stanno nella
memoria episodica. Calcolarla li' vorrebbe dire aprire ogni intervista di ogni
progetto a ogni passata. Quindi la scrive chi possiede il testo, al momento in
cui lo salva.

Le fonti gia' registrate restano NULL: "non si sa cosa contenessero". L'identita'
del set omette la chiave quando l'impronta manca, cosi' questa migrazione non
invalida i piani esistenti - li invalida il primo salvataggio che porta
un'impronta, che e' esattamente il momento in cui l'informazione arriva.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015_source_content_hash"
down_revision = "0014_llm_usage_ledger"
branch_labels = None
depends_on = None

_TABLE = "workspace_sources"
_COLUMN = "content_hash"


def _columns(bind, table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if _COLUMN not in _columns(bind, _TABLE):
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if _COLUMN in _columns(bind, _TABLE):
        op.drop_column(_TABLE, _COLUMN)
