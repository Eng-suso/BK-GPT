"""Il worker d'ingestione vede di chi sono i job in coda, non cosa contengono

Revision ID: 0020_ingest_queue_owners
Revises: 0019_graph_projection_state
Create Date: 2026-11-27

`kg_ingest_queue` ha RLS `FORCE` per consulente (0013): il worker gira come
`delir_app` e, con il contesto di un consulente, vede solo le sue righe. Finche'
il consulente era uno solo bastava drenare quello. Con un account per persona
il worker deve prima sapere **quali** consulenti hanno lavoro in coda.

Lo chiede come `delir_worker`, con il minimo: `SELECT` sulle sole colonne che
dicono di chi e' un job e in che stato si trova, mai sul payload (che e' input
grezzo del cliente). Poi drena ogni consulente nel suo contesto RLS, come prima.
"""

from __future__ import annotations

from alembic import op

revision = "0020_ingest_queue_owners"
down_revision = "0019_graph_projection_state"
branch_labels = None
depends_on = None

_COLUMNS = "consultant_id, status, attempts, processed_at"


def upgrade() -> None:
    op.execute(f"GRANT SELECT ({_COLUMNS}) ON kg_ingest_queue TO delir_worker;")
    op.execute(
        "CREATE POLICY kg_ingest_queue_owners ON kg_ingest_queue "
        "FOR SELECT TO delir_worker USING (true);"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS kg_ingest_queue_owners ON kg_ingest_queue;")
    op.execute(f"REVOKE SELECT ({_COLUMNS}) ON kg_ingest_queue FROM delir_worker;")
