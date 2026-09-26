"""Il piano parziale di una fonte diventa un artefatto.

Revision ID: 0016_plan_extraction_artifacts
Revises: 0015_source_content_hash
Create Date: 2026-09-26

L'estrazione e' la chiamata piu' cara del prodotto: una per intervista, a testo
intero. Finora il suo risultato viveva dentro il merge e moriva li', quindi
ricostruire il piano di un processo con quattro interviste costava quattro
estrazioni anche quando tre non erano cambiate - e nel lavoro vero le fonti si
aggiungono una per volta, mentre l'intervista procede.

La tabella tiene il piano parziale sotto la chiave di cio' che l'ha prodotto:
testo esatto, versione del prompt (schema compreso), modello, ragionamento. Una
chiave che cambia e' un artefatto diverso, non un artefatto da aggiornare: per
questo non c'e' un `updated_at` e la riga non si riscrive mai.

Il tenant e' nella chiave **e** nel vincolo (L8): due clienti con lo stesso
documento non condividono un risultato, e perche' succeda devono sbagliare due
cose invece di una.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016_plan_extraction_artifacts"
down_revision = "0015_source_content_hash"
branch_labels = None
depends_on = None

_TABLE = "workspace_plan_extractions"


def _tables(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    if _TABLE in _tables(bind):
        return
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(), nullable=False, server_default="local"),
        sa.Column("artifact_key", sa.String(), nullable=False),
        sa.Column("source_id", sa.String(), nullable=False, server_default=""),
        sa.Column("source_name", sa.String(), nullable=False, server_default=""),
        sa.Column("input_digest", sa.String(), nullable=False, server_default=""),
        sa.Column("prompt_version", sa.String(), nullable=False, server_default=""),
        sa.Column("model", sa.String(), nullable=False, server_default=""),
        sa.Column("plan_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.UniqueConstraint("tenant_id", "artifact_key", name="uq_plan_extraction_key"),
    )
    op.create_index("ix_workspace_plan_extractions_tenant_id", _TABLE, ["tenant_id"])
    op.create_index("ix_workspace_plan_extractions_artifact_key", _TABLE, ["artifact_key"])


def downgrade() -> None:
    bind = op.get_bind()
    if _TABLE not in _tables(bind):
        return
    op.drop_index("ix_workspace_plan_extractions_artifact_key", table_name=_TABLE)
    op.drop_index("ix_workspace_plan_extractions_tenant_id", table_name=_TABLE)
    op.drop_table(_TABLE)
