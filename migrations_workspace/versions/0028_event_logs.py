"""Gli event log reali caricati sui processi e i template di mapping versionati.

Revision ID: 0028_event_logs
Revises: 0027_merge_client_sources_usage
Create Date: 2026-10-07

SIM-15, secondo sotto-blocco: l'import degli event log diventa persistente.

- `workspace_event_logs`: un file caricato su un processo, con l'anteprima
  (formato, separatore, colonne, righe) e l'esito dell'ultimo mapping (mapping,
  template, qualita', KPI, abbinamento di attivita' e risorse al modello).
  Unico per tenant, processo e impronta del file. Cade con il suo processo.
- `workspace_event_log_payloads`: i byte del file, fuori dalla riga del log.
- `workspace_event_log_templates`: i mapping salvati, una riga per versione.

Nata come `0026_event_logs` su `0025_claim_relations`; rinumerata prima del
merge perche' main nel frattempo aveva gia' unito le sue due 0026 nella 0027.
Le tabelle si creano solo se mancano: un database locale rimasto su
`0026_event_logs` si riallinea con `alembic stamp 0027_merge_client_sources_usage`
seguito da `alembic upgrade head`.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0028_event_logs"
down_revision = "0027_merge_client_sources_usage"
branch_labels = None
depends_on = None

_TEMPLATES = "workspace_event_log_templates"
_LOGS = "workspace_event_logs"
_PAYLOADS = "workspace_event_log_payloads"


def upgrade() -> None:
    # La revision di base crea le tabelle dai modelli (`create_all`): su un
    # database nuovo ci sono gia'.
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if _TEMPLATES not in tables:
        op.create_table(
            _TEMPLATES,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.String(), nullable=False, index=True),
            sa.Column("template_key", sa.String(), nullable=False, index=True),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("mapping_json", sa.Text(), nullable=False),
            sa.Column("columns_json", sa.Text(), nullable=False),
            sa.Column("created_at", sa.String(), nullable=False),
            sa.UniqueConstraint(
                "tenant_id", "template_key", "version", name="uq_workspace_event_log_template_version"
            ),
        )
    if _LOGS not in tables:
        op.create_table(
            _LOGS,
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("tenant_id", sa.String(), nullable=False, index=True),
            sa.Column(
                "process_id",
                sa.String(),
                sa.ForeignKey("workspace_processes.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("format", sa.String(), nullable=False),
            sa.Column("delimiter", sa.String(), nullable=True),
            sa.Column("content_hash", sa.String(), nullable=False),
            sa.Column("byte_size", sa.Integer(), nullable=False),
            sa.Column("row_count", sa.Integer(), nullable=False),
            sa.Column("columns_json", sa.Text(), nullable=False),
            sa.Column("status", sa.String(), nullable=False, server_default="uploaded"),
            sa.Column("mapping_json", sa.Text(), nullable=True),
            sa.Column(
                "template_id",
                sa.Integer(),
                sa.ForeignKey(f"{_TEMPLATES}.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("activity_matches_json", sa.Text(), nullable=True),
            sa.Column("resource_matches_json", sa.Text(), nullable=True),
            sa.Column("bpmn_version_id", sa.Integer(), nullable=True),
            sa.Column("quality_json", sa.Text(), nullable=True),
            sa.Column("summary_json", sa.Text(), nullable=True),
            sa.Column("match_json", sa.Text(), nullable=True),
            sa.Column("resource_match_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.String(), nullable=False),
            sa.Column("mapped_at", sa.String(), nullable=True),
            sa.UniqueConstraint("tenant_id", "process_id", "content_hash", name="uq_workspace_event_log_file"),
        )
    if _PAYLOADS not in tables:
        op.create_table(
            _PAYLOADS,
            sa.Column(
                "event_log_id",
                sa.String(),
                sa.ForeignKey(f"{_LOGS}.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column("tenant_id", sa.String(), nullable=False, index=True),
            sa.Column("payload", sa.LargeBinary(), nullable=False),
        )


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    for table in (_PAYLOADS, _LOGS, _TEMPLATES):
        if table in tables:
            op.drop_table(table)
