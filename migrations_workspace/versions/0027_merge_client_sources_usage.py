"""Riunisce le due 0026 nate in parallelo.

Revision ID: 0027_merge_client_sources_usage
Revises: 0026_client_sources, 0026_usage_context_print
Create Date: 2026-10-07

`0026_client_sources` (P1.16, #72) e `0026_usage_context_print` (P1.3c, #80)
partono entrambe da `0025_claim_relations` e sono entrate su main lo stesso
giorno: due teste, e `alembic upgrade head` si rifiuta di scegliere. Non si
rinumera nessuna delle due, perche' un database puo' averne gia' applicata una:
questa revisione le unisce e basta. Nessuno schema cambia.
"""

from __future__ import annotations

revision = "0027_merge_client_sources_usage"
down_revision = ("0026_client_sources", "0026_usage_context_print")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
