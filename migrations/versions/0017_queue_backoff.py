"""backoff per riga sulle code + il payload dell'outbox deve dichiarare il kind

Revision ID: 0017_queue_backoff
Revises: 0016_claim_assertion_qualifiers
Create Date: 2026-09-10

Due difetti che la coda non poteva vedere da sola.

1. `attempts` diceva quante volte un job era fallito, non quando riprovarlo. Il
   worker riprendeva la riga alla passata successiva — due secondi dopo — e cosi'
   un 429 del provider bruciava i cinque tentativi in una decina di secondi e
   mandava in dead-letter un job che sarebbe passato da solo. `next_attempt_at`
   e' il momento in cui la riga torna eleggibile: il backoff diventa un dato
   della riga, non una speranza del loop.
   `throttled_count` conta a parte i rifiuti per banda: non consumano il budget
   dei tentativi (non sono difetti del job) ma allungano comunque l'attesa, e
   dopo abbastanza rifiuti tornano a consumarlo — altrimenti una chiave con la
   quota esaurita terrebbe la riga in ritentativo per sempre, senza che nessuno
   se ne accorga.

2. `graph_outbox.payload` era `jsonb NOT NULL` e basta. Il projector accetta
   quattro forme (`node`, `edge`, `node_delete`, `edge_delete`) e qualunque
   altra cosa entrata in coda e' un veleno che nessun tentativo potra' mai
   digerire. Il CHECK sposta il rifiuto al momento dell'accodamento, dove c'e'
   ancora un chiamante a cui dirlo.

Il CHECK nasce `NOT VALID`: le righe gia' in coda non vengono rilette (su una
coda grande sarebbe un lock di scansione completa), ma da qui in avanti nessun
INSERT passa senza `kind`.

Da cui il terzo pezzo, `graph_outbox_dead_letter`. Un CHECK `NOT VALID` non
rilegge le righe vecchie, ma le rivaluta appena qualcuno le tocca: il worker che
prova a marcare "non applicabile" una riga gia' corrotta prende una
CheckViolation sull'UPDATE, la transazione salta, e siccome la passata e' una
sola transazione per tutte le righe, **una riga avvelenata ferma l'intera coda**.
Un veleno quindi non si annota sul posto: si sposta. La riga esce da
`graph_outbox` e resta intera qui, con il motivo, per essere diagnosticata — che
e' anche l'unico modo di distinguere "coda in ritardo" da "coda con dentro
qualcosa che non passera' mai".
"""

from __future__ import annotations

from alembic import op

revision = "0017_queue_backoff"
down_revision = "0016_claim_assertion_qualifiers"
branch_labels = None
depends_on = None

_KINDS = "'node','edge','node_delete','edge_delete'"


def upgrade() -> None:
    for table in ("graph_outbox", "mem0_projection_log"):
        op.execute(
            f"ALTER TABLE {table} "
            "ADD COLUMN IF NOT EXISTS next_attempt_at timestamptz NOT NULL DEFAULT now(), "
            "ADD COLUMN IF NOT EXISTS throttled_count int NOT NULL DEFAULT 0;"
        )

    # L'indice del pending ora deve ordinare per eleggibilita', non solo per id.
    op.execute("DROP INDEX IF EXISTS graph_outbox_pending;")
    op.execute(
        "CREATE INDEX graph_outbox_pending ON graph_outbox (next_attempt_at, id) "
        "WHERE processed_at IS NULL;"
    )
    op.execute("DROP INDEX IF EXISTS mem0_log_pending;")
    op.execute(
        "CREATE INDEX mem0_log_pending ON mem0_projection_log (next_attempt_at, id) "
        "WHERE applied_at IS NULL;"
    )

    # COALESCE e non `payload->>'kind' IN (...)` secco: senza la chiave
    # l'espressione vale NULL, e un CHECK che vale NULL passa. Il payload `{}`
    # — esattamente quello che ha riempito la coda di veleni — sarebbe entrato
    # indisturbato attraverso il vincolo che doveva fermarlo.
    op.execute(
        "ALTER TABLE graph_outbox ADD CONSTRAINT graph_outbox_payload_kind "
        f"CHECK (COALESCE(payload->>'kind', '') IN ({_KINDS})) NOT VALID;"
    )

    # Il dead-letter conserva l'id originale: una riga qui e' *quella* riga, non
    # una sua copia rinumerata, e il riferimento nei log resta valido.
    op.execute(
        """
        CREATE TABLE graph_outbox_dead_letter (
          id                bigint PRIMARY KEY,
          aggregate_type    text NOT NULL,
          aggregate_id      uuid NOT NULL,
          consultant_id     uuid NOT NULL,
          client_id         uuid,
          op                text NOT NULL,
          payload           jsonb NOT NULL,
          dedupe_key        text NOT NULL,
          created_at        timestamptz NOT NULL,
          attempts          int NOT NULL,
          last_error        text,
          reason            text NOT NULL,
          dead_lettered_at  timestamptz NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        "GRANT SELECT, INSERT ON graph_outbox_dead_letter TO delir_worker;"
    )


def downgrade() -> None:
    # Le righe messe da parte tornano in coda: scartarle in un downgrade
    # significherebbe perdere l'unica copia di un payload gia' scritto altrove.
    op.execute(
        """
        INSERT INTO graph_outbox
          (aggregate_type, aggregate_id, consultant_id, client_id, op, payload,
           dedupe_key, created_at, attempts, last_error)
        SELECT aggregate_type, aggregate_id, consultant_id, client_id, op, payload,
               dedupe_key, created_at, attempts, last_error
        FROM graph_outbox_dead_letter
        ON CONFLICT (dedupe_key) DO NOTHING;
        """
    )
    op.execute("DROP TABLE IF EXISTS graph_outbox_dead_letter;")
    op.execute(
        "ALTER TABLE graph_outbox DROP CONSTRAINT IF EXISTS graph_outbox_payload_kind;"
    )
    op.execute("DROP INDEX IF EXISTS mem0_log_pending;")
    op.execute(
        "CREATE INDEX mem0_log_pending ON mem0_projection_log (id) "
        "WHERE applied_at IS NULL;"
    )
    op.execute("DROP INDEX IF EXISTS graph_outbox_pending;")
    op.execute(
        "CREATE INDEX graph_outbox_pending ON graph_outbox (id) "
        "WHERE processed_at IS NULL;"
    )
    for table in ("mem0_projection_log", "graph_outbox"):
        op.execute(
            f"ALTER TABLE {table} "
            "DROP COLUMN IF EXISTS throttled_count, "
            "DROP COLUMN IF EXISTS next_attempt_at;"
        )
