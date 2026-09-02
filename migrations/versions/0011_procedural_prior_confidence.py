"""procedural_memory: prior_confidence per il blend degli esiti (L2 fix review)

Revision ID: 0011_procedural_prior_confidence
Revises: 0010_procedural_feedback
Create Date: 2026-09-02

`record_playbook_outcome` (0010) ricalcola `confidence` ad ogni esito come
`(worked + 0.5*partial + prior) / (worked + partial + failed + prior_weight)`
sui contatori CUMULATIVI. Se `prior` fosse la `confidence` corrente della riga,
ogni ricalcolo userebbe come prior un valore gia' derivato dal blend
precedente -> gli stessi esiti verrebbero contati piu' volte e un segnale
iniziale deliberato (es. `save_candidate(confidence=0.9)`) andrebbe perso al
primo esito.

`prior_confidence` fissa quel prior alla confidence impostata alla creazione
del playbook e non viene mai riscritta da `record_playbook_outcome`: il blend
resta una funzione consistente dei soli contatori cumulativi.
"""

from __future__ import annotations

from alembic import op

revision = "0011_procedural_prior_confidence"
down_revision = "0010_procedural_feedback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE procedural_memory "
        "ADD COLUMN prior_confidence double precision NOT NULL DEFAULT 0.5;"
    )
    # backfill: per le righe esistenti l'unico valore disponibile e' la
    # confidence attuale (nessun esito registrato prima di questa migration
    # aveva gia' sporcato la colonna in modo osservabile).
    op.execute("UPDATE procedural_memory SET prior_confidence = confidence;")


def downgrade() -> None:
    op.execute("ALTER TABLE procedural_memory DROP COLUMN IF EXISTS prior_confidence;")
