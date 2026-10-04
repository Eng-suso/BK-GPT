"""Le affermazioni di file diversi, messe a confronto.

Revision ID: 0024_claim_relations
Revises: 0023_source_graph
Create Date: 2026-10-04

P1.13 del piano, il Reconciliation Layer. Un file appena estratto si confronta
con gli altri file confermati dello stesso processo.

- `workspace_claim_relations`: due affermazioni di file diversi sullo stesso
  fatto. `corroboration` se dicono la stessa cosa, `divergence` se no, con il
  tipo dichiarato dal modello e quello che le regole lasciano (puo' solo
  scendere). Le affermazioni cadono con la loro fonte, e le relazioni con loro.
  `kg_contradiction_id`: la contraddizione scritta nel grafo, quando c'e'.
- Sulla fonte, la coda del confronto (`reconcile_status`: `pending | done |
  failed`, tentativi, scadenza, errore), come le altre.
- Sull'affermazione, `kg_claim_id`: il suo Claim nel grafo, per legarci le
  contraddizioni.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0024_claim_relations"
down_revision = "0023_source_graph"
branch_labels = None
depends_on = None

_SOURCES = "workspace_sources"
_CLAIMS = "workspace_source_claims"
_RELATIONS = "workspace_claim_relations"
_SOURCE_ADDITIONS = (
    ("reconcile_status", sa.String(), True, None),
    ("reconcile_attempts", sa.Integer(), False, "0"),
    ("reconcile_next_attempt_at", sa.String(), True, None),
    ("reconcile_error", sa.Text(), True, None),
)
_INDEX = "ix_workspace_sources_reconcile"


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns(_SOURCES)}
    for name, kind, nullable, default in _SOURCE_ADDITIONS:
        if name not in columns:
            op.add_column(_SOURCES, sa.Column(name, kind, nullable=nullable, server_default=default))
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes(_SOURCES)}
    if _INDEX not in indexes:
        op.create_index(_INDEX, _SOURCES, ["reconcile_status", "reconcile_next_attempt_at"])

    if "kg_claim_id" not in {column["name"] for column in sa.inspect(bind).get_columns(_CLAIMS)}:
        op.add_column(_CLAIMS, sa.Column("kg_claim_id", sa.String(), nullable=True))

    if _RELATIONS not in set(sa.inspect(bind).get_table_names()):
        op.create_table(
            _RELATIONS,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.String(), nullable=False, index=True),
            sa.Column("project_id", sa.String(), nullable=False, index=True),
            sa.Column("process_id", sa.String(), nullable=True, index=True),
            sa.Column(
                "claim_id",
                sa.Integer(),
                sa.ForeignKey(f"{_CLAIMS}.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column(
                "other_claim_id",
                sa.Integer(),
                sa.ForeignKey(f"{_CLAIMS}.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("kind", sa.String(), nullable=False),
            sa.Column("declared_type", sa.String(), nullable=True),
            sa.Column("divergence_type", sa.String(), nullable=True),
            sa.Column("reasons_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("explanation", sa.Text(), nullable=False, server_default=""),
            sa.Column("prompt_version", sa.String(), nullable=False),
            sa.Column("created_at", sa.String(), nullable=False),
            sa.Column("kg_contradiction_id", sa.String(), nullable=True),
            sa.UniqueConstraint("claim_id", "other_claim_id", name="uq_claim_relations_pair"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _RELATIONS in set(sa.inspect(bind).get_table_names()):
        op.drop_table(_RELATIONS)
    if "kg_claim_id" in {column["name"] for column in sa.inspect(bind).get_columns(_CLAIMS)}:
        op.drop_column(_CLAIMS, "kg_claim_id")
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes(_SOURCES)}
    if _INDEX in indexes:
        op.drop_index(_INDEX, table_name=_SOURCES)
    columns = {column["name"] for column in sa.inspect(bind).get_columns(_SOURCES)}
    for name, *_ in reversed(_SOURCE_ADDITIONS):
        if name in columns:
            op.drop_column(_SOURCES, name)
