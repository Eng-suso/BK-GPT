"""memory_tombstone + pending_action: cancellazione definitiva e conferma con stato

Revision ID: 0014_memory_lifecycle
Revises: 0013_kg_ingest_queue
Create Date: 2026-09-06

Due difetti del ciclo di vita della memoria consulente, entrambi di stato.

1. `forget_consultant_memory` cancellava solo l'id Mem0 passato. La riga
   canonical restava `active`, il replay di `mem0_projection_log` (INV-2) la
   riproiettava, e Mem0 — che con `infer=True` esplode una frase in piu' fatti —
   teneva i fratelli non cancellati. Risultato: "l'ho eliminata" e poi la stessa
   memoria torna nel recall.

   `memory_tombstone` e' la lapide: l'elenco di cosa il consulente ha chiesto di
   dimenticare, per id Mem0 **e** per hash del testo normalizzato. Il recall
   (gateway.memory_search) la consulta e filtra, quindi la cancellazione regge
   anche se Mem0 riscrive lo stesso fatto sotto un id nuovo o se la proiezione
   viene ricostruita. `mem0_projection_log` non e' utilizzabile per questo:
   delir_app ci ha solo INSERT (0004), non SELECT.

2. La conferma di un'azione distruttiva veniva ricostruita semanticamente dal
   modello al turno dopo ("che cosa stava confermando l'utente?") e si perdeva.
   `pending_action` la rende esplicita: propose congela il bersaglio, confirm
   esegue *quella* riga. Una sola pending per thread; una nuova proposta
   supersede la precedente.
"""

from __future__ import annotations

from alembic import op

revision = "0014_memory_lifecycle"
down_revision = "0013_kg_ingest_queue"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE memory_tombstone (
          id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          consultant_id  uuid NOT NULL REFERENCES consultant(id) ON DELETE CASCADE,
          client_id      uuid REFERENCES client(id) ON DELETE CASCADE,

          -- almeno uno dei due identifica cosa e' stato dimenticato
          mem0_memory_id text,
          statement_hash text NOT NULL,   -- sha256 del testo normalizzato
          statement      text NOT NULL,   -- testo cancellato, per audit
          memory_id      uuid,            -- riga semantic_memory collegata, se nota

          reason         text,
          created_by     text NOT NULL DEFAULT 'consultant'
                         CHECK (created_by IN ('agent','consultant','migration')),
          created_at     timestamptz NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX memory_tombstone_mem0_id ON memory_tombstone "
        "(consultant_id, mem0_memory_id) WHERE mem0_memory_id IS NOT NULL;"
    )
    op.execute(
        "CREATE INDEX memory_tombstone_hash ON memory_tombstone "
        "(consultant_id, statement_hash);"
    )

    op.execute(
        """
        CREATE TABLE pending_action (
          id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          consultant_id  uuid NOT NULL REFERENCES consultant(id) ON DELETE CASCADE,
          client_id      uuid REFERENCES client(id) ON DELETE CASCADE,
          thread_id      text NOT NULL,

          action         text NOT NULL,
          params         jsonb NOT NULL,   -- bersaglio congelato al momento della proposta
          preview        text NOT NULL,    -- testo esatto mostrato all'utente
          status         text NOT NULL DEFAULT 'pending'
                         CHECK (status IN ('pending','confirmed','cancelled',
                                           'expired','superseded')),
          result         jsonb,

          created_at     timestamptz NOT NULL DEFAULT now(),
          expires_at     timestamptz NOT NULL,
          resolved_at    timestamptz
        );
        """
    )
    # una sola azione in attesa per thread: la proposta nuova supersede la vecchia
    op.execute(
        "CREATE UNIQUE INDEX pending_action_one_open ON pending_action "
        "(consultant_id, thread_id) WHERE status = 'pending';"
    )
    op.execute(
        "CREATE INDEX pending_action_lookup ON pending_action "
        "(consultant_id, thread_id, created_at DESC);"
    )

    # RLS: stesso predicato delle tabelle di memoria (0005) — le righe
    # consultant-scoped (client_id NULL) restano visibili in ogni contesto.
    pred = (
        "consultant_id = app_consultant_id() "
        "AND (client_id IS NULL OR client_id = app_client_id())"
    )
    for table in ("memory_tombstone", "pending_action"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        op.execute(
            f"CREATE POLICY {table}_tenant ON {table} "
            f"USING ({pred}) WITH CHECK ({pred});"
        )
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO delir_app;")


def downgrade() -> None:
    for table in ("pending_action", "memory_tombstone"):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
