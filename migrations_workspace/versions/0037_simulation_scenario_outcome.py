"""L'esito osservato di un'alternativa implementata (SIM-28).

Revision ID: 0037_simulation_scenario_outcome
Revises: 0036_owner_dashboard_links
Create Date: 2026-10-22

Un'alternativa del workspace, una volta implementata dal cliente, riceve la
data dell'implementazione, la previsione con cui e' stata decisa e i KPI del log
reale prima e dopo: quanto aveva ragione il simulatore. Una colonna JSON sullo
scenario, perche' l'esito vive e muore con l'alternativa.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0037_simulation_scenario_outcome"
down_revision = "0036_owner_dashboard_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0001 crea le tabelle dai metadati ORM su un database nuovo, colonna compresa.
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("workspace_simulation_scenarios")}
    if "outcome_json" in columns:
        return
    op.add_column("workspace_simulation_scenarios", sa.Column("outcome_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("workspace_simulation_scenarios", "outcome_json")
