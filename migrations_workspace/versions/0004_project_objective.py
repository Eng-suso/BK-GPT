"""L'obiettivo dell'incarico diventa un campo del progetto.

Revision ID: 0004_project_objective
Revises: 0003_review_answers
Create Date: 2026-09-06

Il progetto conservava nome, fase, stato, avanzamento, prossimo passo,
milestone, issue e deliverable: il contenitore, non l'incarico. Quando il
consulente dettava l'obiettivo ("ricostruire l'AS-IS, validarlo, simularlo e
misurare i KPI") quella frase restava nella chat history e non nel record, e la
Project Chat aperta il giorno dopo non sapeva piu' perche' il progetto esistesse
(bug PROJECT-01).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_project_objective"
down_revision = "0003_review_answers"
branch_labels = None
depends_on = None

_TABLE = "workspace_projects"
_COLUMN = "objective"


def _has_column(bind, table: str, column: str) -> bool:
    """
    Determine whether a table contains a specified column.
    
    Parameters:
    	bind: Database connection or engine used for schema inspection.
    	table (str): Name of the table to inspect.
    	column (str): Name of the column to find.
    
    Returns:
    	bool: `true` if the column exists in the table, `false` otherwise.
    """
    return column in {col["name"] for col in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    """Add the non-nullable project objective column to the workspace projects table if needed."""
    bind = op.get_bind()
    if not _has_column(bind, _TABLE, _COLUMN):
        op.add_column(
            _TABLE,
            sa.Column(_COLUMN, sa.Text(), nullable=False, server_default=""),
        )
        op.alter_column(_TABLE, _COLUMN, server_default=None)


def downgrade() -> None:
    """Remove the project objective column if it exists."""
    bind = op.get_bind()
    if _has_column(bind, _TABLE, _COLUMN):
        op.drop_column(_TABLE, _COLUMN)
