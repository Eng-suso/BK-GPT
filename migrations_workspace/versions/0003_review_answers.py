"""Risposte del consulente alle domande aperte del piano.

Revision ID: 0003_review_answers
Revises: 0002_bpmn_review_versions
Create Date: 2026-09-06

`missing_information` era una lista di testo che si poteva solo leggere. Una
domanda aperta ora si puo' chiudere: l'agente propone le alternative, il
consulente sceglie, e la scelta viene registrata sulla review (e nel suo
storico) separata da cio' che il modello ha estratto da solo.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_review_answers"
down_revision = "0002_bpmn_review_versions"
branch_labels = None
depends_on = None

_TABLES = ("workspace_bpmn_reviews", "workspace_bpmn_review_versions")


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
    """Add the answers JSON column to each review table when absent."""
    bind = op.get_bind()
    for table in _TABLES:
        if not _has_column(bind, table, "answers_json"):
            op.add_column(
                table,
                sa.Column("answers_json", sa.Text(), nullable=False, server_default="[]"),
            )
            op.alter_column(table, "answers_json", server_default=None)


def downgrade() -> None:
    """Remove the answers column from review tables when present."""
    bind = op.get_bind()
    for table in _TABLES:
        if _has_column(bind, table, "answers_json"):
            op.drop_column(table, "answers_json")
