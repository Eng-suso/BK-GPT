"""Il consulente nel registro dei consumi.

Revision ID: 0038_usage_user
Revises: 0037_simulation_scenario_outcome
Create Date: 2026-11-26

Il registro sapeva per quale tenant si era speso, non per chi. Il limite d'uso
della prova (sessione di cinque ore, settimana) e' per persona: senza la
colonna, «quanto ha usato questo consulente dalle 10» non era una query. L'indice
e' su `(user_id, created_at)` perche' e' esattamente la forma di quella domanda.

Le righe scritte prima restano con `user_id` NULL: non si inventa a posteriori
chi le ha spese.

`workspace_sources.uploaded_by` per la stessa ragione: lettura ed estrazione di
una fonte girano in un worker, senza richiesta, e la loro spesa va a chi l'ha
caricata.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0038_usage_user"
down_revision = "0037_simulation_scenario_outcome"
branch_labels = None
depends_on = None

_USAGE = "workspace_llm_usage"
_INDEX = "ix_workspace_llm_usage_user_created"
_SOURCES = "workspace_sources"


def upgrade() -> None:
    # 0001 crea le tabelle dai metadati ORM su un database nuovo, colonna compresa.
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns(_USAGE)}
    if "user_id" not in columns:
        op.add_column(_USAGE, sa.Column("user_id", sa.String(), nullable=True))
    indexes = {index["name"] for index in inspector.get_indexes(_USAGE)}
    if _INDEX not in indexes:
        op.create_index(_INDEX, _USAGE, ["user_id", "created_at"])
    if "uploaded_by" not in {column["name"] for column in inspector.get_columns(_SOURCES)}:
        op.add_column(_SOURCES, sa.Column("uploaded_by", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column(_SOURCES, "uploaded_by")
    op.drop_index(_INDEX, table_name=_USAGE)
    op.drop_column(_USAGE, "user_id")
