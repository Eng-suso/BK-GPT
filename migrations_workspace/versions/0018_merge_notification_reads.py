"""Riunisce le due teste nate su 0013: gli avvisi letti e la fila di P2.

Revision ID: 0018_merge_notification_reads
Revises: 0017_source_audit_artifacts, 0014_notification_reads
Create Date: 2026-10-02

`0014_notification_reads` (feat/notifications-feed) e `0014_llm_usage_ledger`
sono nate in parallelo sulla stessa base. L'id della prima non si rinomina: il
database `workspace` di sviluppo l'ha gia' applicata, e un id sparito lo
lascerebbe senza una revisione da cui ripartire. Da qui in poi la fila e' una.

E' una revisione di sola fusione: `upgrade` non tocca lo schema, `downgrade`
riporta soltanto le due teste separate.
"""

from __future__ import annotations

revision = "0018_merge_notification_reads"
down_revision = ("0017_source_audit_artifacts", "0014_notification_reads")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
