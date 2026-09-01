"""procedural_memory: contatori usage + outcome (L2 / P7.4)

Revision ID: 0010_procedural_feedback
Revises: 0009_queue_retention
Create Date: 2026-09-02

Feedback loop dei playbook appresi: quante volte un playbook 'active' e' stato
iniettato nel prompt (`used_count` / `last_used_at`) e come e' andata
(`outcome_worked` / `outcome_partial` / `outcome_failed` / `last_outcome_at`).

Colonne sulla riga (non una tabella a parte): ereditano la RLS di
procedural_memory (migration 0005), nessun grant nuovo. `record_playbook_outcome`
aggiorna `confidence` con una media mobile e puo' auto-deprecare un playbook con
confidence bassa e troppi esiti negativi.
"""

from __future__ import annotations

from alembic import op

revision = "0010_procedural_feedback"
down_revision = "0009_queue_retention"
branch_labels = None
depends_on = None

_COLUMNS = (
    "used_count integer NOT NULL DEFAULT 0",
    "outcome_worked integer NOT NULL DEFAULT 0",
    "outcome_partial integer NOT NULL DEFAULT 0",
    "outcome_failed integer NOT NULL DEFAULT 0",
    "last_used_at timestamptz",
    "last_outcome_at timestamptz",
)


def upgrade() -> None:
    for column in _COLUMNS:
        op.execute(f"ALTER TABLE procedural_memory ADD COLUMN {column};")


def downgrade() -> None:
    for column in _COLUMNS:
        name = column.split()[0]
        op.execute(f"ALTER TABLE procedural_memory DROP COLUMN IF EXISTS {name};")
