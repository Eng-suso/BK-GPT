"""La coda delle simulazioni su Postgres (P0.3).

Revision ID: 0034_simulation_run_queue
Revises: 0033_simulation_run_model
Create Date: 2026-10-10

Prima un run girava in un BackgroundTask del processo web: oltre il massimo di
run insieme la richiesta riceveva 429, e un riavvio a meta' lasciava il run
``pending`` finche' non scadeva. Ora il run entra in coda con cio' che serve per
eseguirlo (il BPMN normalizzato), chi lo prende lo marca ``started_at`` e batte
``heartbeat_at`` finche' gira; un run che tace torna in coda.

I run ``pending`` gia' presenti non hanno il BPMN per ripartire: si segnano come
avviati alla loro creazione, cosi' lo spazzino li chiude come prima.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0034_simulation_run_queue"
down_revision = "0033_simulation_run_model"
branch_labels = None
depends_on = None

_COLUMNS = (
    sa.Column("bpmn_xml", sa.Text(), nullable=True),
    sa.Column("started_at", sa.String(), nullable=True),
    sa.Column("heartbeat_at", sa.String(), nullable=True),
    sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("worker_id", sa.String(), nullable=True),
)


def upgrade() -> None:
    # 0001 usa i metadati ORM correnti su un database nuovo, colonne comprese.
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("workspace_simulation_runs")}
    for column in _COLUMNS:
        if column.name not in existing:
            op.add_column("workspace_simulation_runs", column)
    op.execute(
        "UPDATE workspace_simulation_runs SET started_at = created_at "
        "WHERE status = 'pending' AND started_at IS NULL"
    )
    op.create_index(
        "ix_workspace_simulation_runs_queue",
        "workspace_simulation_runs",
        ["id"],
        postgresql_where=sa.text("status = 'pending' AND started_at IS NULL"),
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_workspace_simulation_runs_queue", table_name="workspace_simulation_runs", if_exists=True)
    for column in reversed(_COLUMNS):
        op.drop_column("workspace_simulation_runs", column.name)
