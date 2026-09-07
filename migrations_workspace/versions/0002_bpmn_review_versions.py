"""BPMN review versionata: storico + versione corrente.

Revision ID: 0002_bpmn_review_versions
Revises: 0001_workspace_schema
Create Date: 2026-09-05

Una review era uno slot unico per `bpmn_model_id`: ogni `prepare` sovrascriveva
il piano precedente, quindi non c'era modo di iterarlo ne' di confrontarlo con
cio' che aveva sostituito. Stessa forma gia' usata per il modello BPMN
(`workspace_bpmn_models` + `workspace_bpmn_versions`): la riga corrente resta
dov'e' e ogni stato passato finisce nello storico.

Le tabelle nuove le materializza `create_all` dai modelli (come 0001). La colonna
su una tabella esistente no: va aggiunta esplicitamente, con backfill a 1 per le
review gia' presenti.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_bpmn_review_versions"
down_revision = "0001_workspace_schema"
branch_labels = None
depends_on = None


def _review_version_table():
    """Return the database table definition for BPMN review versions."""
    from backend.workspace_storage import WorkspaceBpmnReviewVersion

    return WorkspaceBpmnReviewVersion.__table__


def _has_column(bind, table: str, column: str) -> bool:
    """
    Determine whether a table contains a specified column.
    
    Parameters:
    	table (str): Name of the table to inspect.
    	column (str): Name of the column to find.
    
    Returns:
    	bool: `true` if the table contains the column, `false` otherwise.
    """
    return column in {col["name"] for col in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    """
    Create the BPMN review version history table and add the review version column.
    
    The existing review rows are initialized with version 1, after which the database default is removed so future versions are assigned by the application.
    """
    bind = op.get_bind()
    _review_version_table().create(bind, checkfirst=True)

    if not _has_column(bind, "workspace_bpmn_reviews", "version"):
        # server_default per le righe esistenti, poi rimosso: la versione la
        # assegna l'applicazione, non il database.
        op.add_column(
            "workspace_bpmn_reviews",
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        )
        op.alter_column("workspace_bpmn_reviews", "version", server_default=None)


def downgrade() -> None:
    """Remove BPMN review versioning schema changes.
    
    Drops the review version column when present and removes the BPMN review history table if it exists.
    """
    bind = op.get_bind()
    if _has_column(bind, "workspace_bpmn_reviews", "version"):
        op.drop_column("workspace_bpmn_reviews", "version")
    _review_version_table().drop(bind, checkfirst=True)
