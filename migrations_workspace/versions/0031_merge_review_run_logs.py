"""Riunisce le due 0030 nate in parallelo.

Revision ID: 0031_merge_review_run_logs
Revises: 0030_review_proposal_diagrams, 0030_simulation_run_logs
Create Date: 2026-10-08

`0030_review_proposal_diagrams` (#93) e `0030_simulation_run_logs` (SIM-06,
#92) partono entrambe da `0029_impact_review_actions` e sono entrate su main
la stessa mattina: due teste, e `alembic upgrade head` si rifiuta di scegliere.
Non si rinumera nessuna delle due, perche' un database puo' averne gia'
applicata una: questa revisione le unisce e basta. Nessuno schema cambia.
"""

from __future__ import annotations

revision = "0031_merge_review_run_logs"
down_revision = ("0030_review_proposal_diagrams", "0030_simulation_run_logs")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
