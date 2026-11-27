"""I token scritti in cache, nel registro dei consumi.

Revision ID: 0041_usage_cache_write
Revises: 0040_usage_audio
Create Date: 2026-11-27

Anthropic fattura la scrittura in cache a parte (1,25 volte l'ingresso con la
durata di 5 minuti). Senza questa colonna il registro conterebbe quei token al
prezzo di input e sotto-conterebbe Claude rispetto alla fattura.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0041_usage_cache_write"
down_revision = "0040_usage_audio"
branch_labels = None
depends_on = None

_USAGE = "workspace_llm_usage"


def upgrade() -> None:
    # 0001 crea le tabelle dai metadati ORM su un database nuovo, colonne comprese.
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns(_USAGE)}
    if "cache_write_input_tokens" not in columns:
        op.add_column(
            _USAGE,
            sa.Column("cache_write_input_tokens", sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    op.drop_column(_USAGE, "cache_write_input_tokens")
