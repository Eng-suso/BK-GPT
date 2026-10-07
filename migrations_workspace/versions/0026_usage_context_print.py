"""Il registro dei consumi ricorda quale contesto ha visto il modello.

Revision ID: 0026_usage_context_print
Revises: 0025_claim_relations
Create Date: 2026-10-07

P1.3c del piano backend. `prompt_version` dice quale prompt fisso ha girato;
non dice cosa il turno ha mandato al modello oltre a quello. Il contesto di
scope ha gia' un'impronta sha256 (`context_budget.assemble`): finisce in una
colonna, cosi' due turni con la stessa impronta si riconoscono come lo stesso
contesto, e un turno che costa il doppio si spiega con cio' che ha ricevuto.

Nessun backfill: le righe di prima restano NULL, come quelle dei compiti che il
contesto di scope non lo ricevono.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0026_usage_context_print"
down_revision = "0025_claim_relations"
branch_labels = None
depends_on = None

_USAGE = "workspace_llm_usage"
_INDEX = "ix_workspace_llm_usage_context_fingerprint"


def upgrade() -> None:
    # La revision di base crea le tabelle dai modelli (`create_all`): su un
    # database nuovo la colonna c'e' gia', come per la 0024.
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns(_USAGE)}
    if "context_fingerprint" not in columns:
        op.add_column(_USAGE, sa.Column("context_fingerprint", sa.String(), nullable=True))
    indexes = {index["name"] for index in inspector.get_indexes(_USAGE)}
    if _INDEX not in indexes:
        op.create_index(_INDEX, _USAGE, ["context_fingerprint"])


def downgrade() -> None:
    op.drop_index(_INDEX, table_name=_USAGE)
    op.drop_column(_USAGE, "context_fingerprint")
