"""L'audio nel registro e nel piano d'uso, in secondi e in ore.

Revision ID: 0040_usage_audio
Revises: 0039_usage_plans
Create Date: 2026-11-27

La trascrizione si paga a minuto, non a token: il registro conta i secondi di
audio di ogni riga (`audio_seconds`), e il piano d'uso ha un tetto in ore per la
settimana e per la prova, separato dal budget dei modelli. NULL = default dei
settings, 0 = nessun tetto.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0040_usage_audio"
down_revision = "0039_usage_plans"
branch_labels = None
depends_on = None

_USAGE = "workspace_llm_usage"
_PLANS = "workspace_usage_plans"


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    # 0001 crea le tabelle dai metadati ORM su un database nuovo, colonne comprese.
    if "audio_seconds" not in _columns(_USAGE):
        op.add_column(_USAGE, sa.Column("audio_seconds", sa.Integer(), nullable=False, server_default="0"))
    plans = _columns(_PLANS)
    for column in ("week_audio_hours", "trial_audio_hours"):
        if column not in plans:
            op.add_column(_PLANS, sa.Column(column, sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column(_PLANS, "trial_audio_hours")
    op.drop_column(_PLANS, "week_audio_hours")
    op.drop_column(_USAGE, "audio_seconds")
