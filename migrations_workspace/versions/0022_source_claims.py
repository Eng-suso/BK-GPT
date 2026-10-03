"""Le affermazioni di un file caricato, ognuna legata alla porzione da cui viene.

Revision ID: 0022_source_claims
Revises: 0021_chat_message_attachments
Create Date: 2026-10-02

P1.12 del piano: il Semantic Layer. Ogni affermazione cita una porzione
dell'Evidence Bucket (`workspace_evidence_segments`): senza ancora non esiste.

- `workspace_source_claims`: l'affermazione, la porzione citata (ordinale e
  ancora, cosi' resta leggibile anche se la porzione viene riscritta), la
  citazione e se e' stata ritrovata parola per parola nella porzione.
- Sulla fonte, la coda dell'estrazione (`claims_status`: `pending | done |
  failed`, tentativi, scadenza, errore), come quella della lettura.
- `confirm_when_read`: il file e' partito in chat mentre era ancora in lettura.
  Inviarlo vale come conferma, ma una fonte non letta non si conferma: la
  conferma scatta quando la lettura finisce.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0022_source_claims"
down_revision = "0021_chat_message_attachments"
branch_labels = None
depends_on = None

_SOURCES = "workspace_sources"
_ADDITIONS = (
    ("claims_status", sa.String(), True, None),
    ("claims_attempts", sa.Integer(), False, "0"),
    ("claims_next_attempt_at", sa.String(), True, None),
    ("claims_error", sa.Text(), True, None),
    ("confirm_when_read", sa.Boolean(), False, sa.false()),
)


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns(_SOURCES)}
    for name, kind, nullable, default in _ADDITIONS:
        if name not in columns:
            op.add_column(_SOURCES, sa.Column(name, kind, nullable=nullable, server_default=default))
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes(_SOURCES)}
    if "ix_workspace_sources_claims" not in indexes:
        op.create_index(
            "ix_workspace_sources_claims", _SOURCES, ["claims_status", "claims_next_attempt_at"]
        )

    if "workspace_source_claims" not in set(sa.inspect(bind).get_table_names()):
        op.create_table(
            "workspace_source_claims",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.String(), nullable=False, index=True),
            sa.Column(
                "source_id",
                sa.String(),
                sa.ForeignKey("workspace_sources.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("ordinal", sa.Integer(), nullable=False),
            sa.Column("statement", sa.Text(), nullable=False),
            sa.Column("segment_ordinal", sa.Integer(), nullable=False),
            sa.Column("anchor_ref", sa.String(), nullable=False),
            sa.Column("quote", sa.Text(), nullable=False),
            sa.Column("quote_verified", sa.Boolean(), nullable=False),
            sa.Column("content_hash", sa.String(), nullable=False),
            sa.Column("prompt_version", sa.String(), nullable=False),
            sa.Column("extracted_at", sa.String(), nullable=False),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if "workspace_source_claims" in set(sa.inspect(bind).get_table_names()):
        op.drop_table("workspace_source_claims")
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes(_SOURCES)}
    if "ix_workspace_sources_claims" in indexes:
        op.drop_index("ix_workspace_sources_claims", table_name=_SOURCES)
    columns = {column["name"] for column in sa.inspect(bind).get_columns(_SOURCES)}
    for name, *_ in reversed(_ADDITIONS):
        if name in columns:
            op.drop_column(_SOURCES, name)
