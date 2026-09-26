"""Il giudizio del revisore su una fonte diventa un artefatto.

Revision ID: 0017_source_audit_artifacts
Revises: 0016_plan_extraction_artifacts
Create Date: 2026-09-26

Il revisore di conformita' legge ogni fonte per intero contro gli elementi del
piano. Il confronto si rifa' ogni volta che il canvas cambia o che lo si chiede
di nuovo, e rileggeva anche le fonti che niente aveva toccato: stesso testo,
stesso piano, stesso prompt, stessa risposta pagata di nuovo.

La tabella tiene il verdetto grezzo dell'agente sotto la chiave di cio' che l'ha
prodotto. Come per i piani parziali, una chiave diversa e' un artefatto diverso,
la riga non si riscrive mai, e il tenant e' sia nella chiave sia nel vincolo.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017_source_audit_artifacts"
down_revision = "0016_plan_extraction_artifacts"
branch_labels = None
depends_on = None

_TABLE = "workspace_source_audits"


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
        sa.Column("prompt_version", sa.String(), nullable=False, server_default=""),
        sa.Column("model", sa.String(), nullable=False, server_default=""),
        sa.Column("verdict_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.UniqueConstraint("tenant_id", "artifact_key", name="uq_source_audit_key"),
    )
    op.create_index("ix_workspace_source_audits_tenant_id", _TABLE, ["tenant_id"])
    op.create_index("ix_workspace_source_audits_artifact_key", _TABLE, ["artifact_key"])


def downgrade() -> None:
    bind = op.get_bind()
    if _TABLE not in _tables(bind):
        return
    op.drop_index("ix_workspace_source_audits_artifact_key", table_name=_TABLE)
    op.drop_index("ix_workspace_source_audits_tenant_id", table_name=_TABLE)
    op.drop_table(_TABLE)
