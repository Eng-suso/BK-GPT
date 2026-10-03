"""Le affermazioni di un file vanno nel grafo: la coda di quel passaggio.

Revision ID: 0023_source_graph
Revises: 0022_source_claims
Create Date: 2026-10-03

P1.14 del piano. Finita l'estrazione (P1.12), la fonte entra nella coda del
grafo: fonte, porzioni citate e affermazioni vanno nel canonical, e da li' in
Neo4j. Stessa forma delle altre code sulla fonte (`graph_status`: `pending |
done | failed`, tentativi, scadenza, errore). `None` finche' non ci sono
affermazioni da portare.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0023_source_graph"
down_revision = "0022_source_claims"
branch_labels = None
depends_on = None

_SOURCES = "workspace_sources"
_ADDITIONS = (
    ("graph_status", sa.String(), True, None),
    ("graph_attempts", sa.Integer(), False, "0"),
    ("graph_next_attempt_at", sa.String(), True, None),
    ("graph_error", sa.Text(), True, None),
)
_INDEX = "ix_workspace_sources_graph"


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns(_SOURCES)}
    for name, kind, nullable, default in _ADDITIONS:
        if name not in columns:
            op.add_column(_SOURCES, sa.Column(name, kind, nullable=nullable, server_default=default))
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes(_SOURCES)}
    if _INDEX not in indexes:
        op.create_index(_INDEX, _SOURCES, ["graph_status", "graph_next_attempt_at"])


def downgrade() -> None:
    bind = op.get_bind()
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes(_SOURCES)}
    if _INDEX in indexes:
        op.drop_index(_INDEX, table_name=_SOURCES)
    columns = {column["name"] for column in sa.inspect(bind).get_columns(_SOURCES)}
    for name, *_ in reversed(_ADDITIONS):
        if name in columns:
            op.drop_column(_SOURCES, name)
