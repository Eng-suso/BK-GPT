"""Una fonte puo' appartenere al cliente, non solo a un progetto.

Revision ID: 0026_client_sources
Revises: 0025_claim_relations
Create Date: 2026-10-04

P1.16 del piano, il livello cliente (decisione del 4 ottobre). Un file caricato
"per tutto il cliente" non e' di nessun progetto: compare nelle Fonti di ogni
progetto del cliente e sopravvive alla cancellazione di uno di loro.

- `workspace_sources.client_id`: il cliente a cui la fonte appartiene. Si
  riempie anche per le fonti di progetto (il cliente del progetto), cosi' "le
  fonti di questo cliente" e' una domanda sola.
- `workspace_sources.project_id` diventa facoltativo: vuoto per le fonti del
  cliente. Almeno uno dei due c'e' sempre.
- Le fonti del cliente si deduplicano per contenuto dentro il cliente, come
  quelle di progetto dentro il progetto.
- `workspace_claim_relations.project_id` diventa facoltativo: una relazione fra
  due fonti del cliente non e' di nessun progetto.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0026_client_sources"
down_revision = "0025_claim_relations"
branch_labels = None
depends_on = None

_SOURCES = "workspace_sources"
_INDEX = "ix_workspace_sources_client_id"
_CLIENT_UNIQUE = "uq_workspace_source_client_ingestion"
_CHECK = "ck_workspace_sources_owner"


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns(_SOURCES)}
    if "client_id" not in columns:
        op.add_column(
            _SOURCES,
            sa.Column("client_id", sa.String(), sa.ForeignKey("workspace_clients.id"), nullable=True),
        )
    op.execute(
        "UPDATE workspace_sources s SET client_id = p.client_id "
        "FROM workspace_projects p WHERE p.id = s.project_id AND s.client_id IS NULL"
    )
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes(_SOURCES)}
    if _INDEX not in indexes:
        op.create_index(_INDEX, _SOURCES, ["client_id"])
    op.alter_column(_SOURCES, "project_id", existing_type=sa.String(), nullable=True)
    op.create_check_constraint(_CHECK, _SOURCES, "project_id IS NOT NULL OR client_id IS NOT NULL")
    # Il vincolo per progetto non vede le fonti senza progetto (NULL e' sempre
    # diverso da NULL): per loro vale il cliente.
    op.create_index(
        _CLIENT_UNIQUE,
        _SOURCES,
        ["tenant_id", "client_id", "ingestion_key"],
        unique=True,
        postgresql_where=sa.text("project_id IS NULL"),
    )
    op.alter_column("workspace_claim_relations", "project_id", existing_type=sa.String(), nullable=True)


def downgrade() -> None:
    # Le fonti del cliente non hanno un progetto in cui tornare: senza la loro
    # colonna non esisterebbero piu', e un downgrade le perderebbe in silenzio.
    op.execute("DELETE FROM workspace_claim_relations WHERE project_id IS NULL")
    op.execute("DELETE FROM workspace_sources WHERE project_id IS NULL")
    op.alter_column("workspace_claim_relations", "project_id", existing_type=sa.String(), nullable=False)
    op.drop_index(_CLIENT_UNIQUE, table_name=_SOURCES)
    op.drop_constraint(_CHECK, _SOURCES, type_="check")
    op.alter_column(_SOURCES, "project_id", existing_type=sa.String(), nullable=False)
    op.drop_index(_INDEX, table_name=_SOURCES)
    op.drop_column(_SOURCES, "client_id")
