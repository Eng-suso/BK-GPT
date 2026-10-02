"""Acquisizione delle fonti in background, con le evidenze ancorate salvate.

Revision ID: 0020_source_acquisition
Revises: 0019_source_ingestion

Leggere un PDF con layout, tabelle e OCR costa secondi o minuti: dentro la
richiesta di caricamento teneva occupato un thread dell'API per tutto quel
tempo. Ora il caricamento conserva l'originale e mette la fonte in coda; il
worker la legge e scrive qui il risultato.

- Sulla fonte, lo stato dell'acquisizione (`pending`, `done`, `partial`,
  `failed`) con tentativi, scadenza del lease e ultimo errore. Come la coda dei
  piani: niente stato `running`, una presa in carico scade da sola.
- `workspace_source_evidence`: la rappresentazione canonica della fonte (una
  riga per fonte), con struttura e problemi di acquisizione.
- `workspace_evidence_segments`: le porzioni citabili, una riga ciascuna, con la
  loro ancora. Un'affermazione estratta cita una di queste righe.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020_source_acquisition"
down_revision = "0019_source_ingestion"
branch_labels = None
depends_on = None

_SOURCES = "workspace_sources"
_ADDITIONS = (
    ("acquisition_status", sa.String(), True, None),
    ("acquisition_attempts", sa.Integer(), False, "0"),
    ("acquisition_next_attempt_at", sa.String(), True, None),
    ("acquisition_error", sa.Text(), True, None),
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns(_SOURCES)}
    for name, kind, nullable, default in _ADDITIONS:
        if name not in columns:
            op.add_column(_SOURCES, sa.Column(name, kind, nullable=nullable, server_default=default))
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes(_SOURCES)}
    if "ix_workspace_sources_acquisition" not in indexes:
        op.create_index(
            "ix_workspace_sources_acquisition",
            _SOURCES,
            ["acquisition_status", "acquisition_next_attempt_at"],
        )
    # Le fonti caricate prima di questa migrazione sono gia' state lette dentro
    # la richiesta: il loro testo c'e'. Rimetterle in coda le renderebbe non
    # confermabili finche' il worker non le rilegge, e con il lettore dei
    # documenti spento finirebbero "non leggibili" pur avendo un testo valido.
    # Restano lette; le evidenze ancorate arrivano ricaricando il file.
    op.execute(
        "UPDATE workspace_sources SET acquisition_status = 'done' "
        "WHERE storage_key IS NOT NULL AND acquisition_status IS NULL "
        "AND extracted_text IS NOT NULL"
    )

    tables = set(sa.inspect(bind).get_table_names())
    if "workspace_source_evidence" not in tables:
        op.create_table(
            "workspace_source_evidence",
            sa.Column("source_id", sa.String(), sa.ForeignKey("workspace_sources.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("tenant_id", sa.String(), nullable=False, index=True),
            sa.Column("schema_version", sa.Integer(), nullable=False),
            sa.Column("format", sa.String(), nullable=False),
            sa.Column("parser", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("content_hash", sa.String(), nullable=False),
            sa.Column("structure_json", sa.Text(), nullable=False),
            sa.Column("issues_json", sa.Text(), nullable=False),
            sa.Column("acquired_at", sa.String(), nullable=False),
        )
    if "workspace_evidence_segments" not in tables:
        op.create_table(
            "workspace_evidence_segments",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.String(), nullable=False, index=True),
            sa.Column(
                "source_id",
                sa.String(),
                sa.ForeignKey("workspace_sources.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("ordinal", sa.Integer(), nullable=False),
            sa.Column("anchor_kind", sa.String(), nullable=False),
            sa.Column("anchor_ref", sa.String(), nullable=False),
            sa.Column("locator_json", sa.Text(), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("value_type", sa.String(), nullable=False),
            sa.Column("value_json", sa.Text(), nullable=True),
            sa.Column("attributes_json", sa.Text(), nullable=False),
        )
        op.create_index(
            "ix_evidence_segments_source_ref",
            "workspace_evidence_segments",
            ["source_id", "anchor_ref"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "workspace_evidence_segments" in tables:
        op.drop_table("workspace_evidence_segments")
    if "workspace_source_evidence" in tables:
        op.drop_table("workspace_source_evidence")
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes(_SOURCES)}
    if "ix_workspace_sources_acquisition" in indexes:
        op.drop_index("ix_workspace_sources_acquisition", table_name=_SOURCES)
    columns = {column["name"] for column in sa.inspect(bind).get_columns(_SOURCES)}
    for name, *_ in reversed(_ADDITIONS):
        if name in columns:
            op.drop_column(_SOURCES, name)
