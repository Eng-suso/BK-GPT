"""Coda di ingestione asincrona dell'evidenza KG (P5)

Revision ID: 0013_kg_ingest_queue
Revises: 0012_scope_canonical_unique_keys
Create Date: 2026-09-03

Oggi il tool evidenza (`manage_process_evidence` / `manage_project_evidence`)
chiama `canonical.write_evidence` **sincrono nel giro dell'agente**: chunk +
embedding + entity resolution (chiamate LLM, P2) + write atomico. Un turno
dell'agente si blocca per secondi.

`kg_ingest_queue` disaccoppia: il tool risolve lo scope (veloce) e accoda il
payload; `backend/workers/ingest_worker.py` (ruolo `delir_app`, ha bisogno
della DML di dominio per `write_evidence`) drena e fa il lavoro pesante, con
retry e dead-letter come le altre due code.

Non e' un outbox come `graph_outbox` (payload gia' B+-safe, worker senza
accesso al dominio): qui il payload e' l'input grezzo e il worker esegue la
logica di dominio -> RLS `FORCE` con il pattern strict-client (come `project`),
cosi' l'app vede solo le proprie righe e il worker, con contesto solo-consultant,
vede tutte quelle del consulente.
"""

from __future__ import annotations

from alembic import op

revision = "0013_kg_ingest_queue"
down_revision = "0012_scope_canonical_unique_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE kg_ingest_queue (
          id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          consultant_id  uuid NOT NULL REFERENCES consultant(id) ON DELETE CASCADE,
          client_id      uuid REFERENCES client(id)  ON DELETE CASCADE,
          project_id     uuid REFERENCES project(id) ON DELETE SET NULL,
          process_id     uuid REFERENCES process(id) ON DELETE SET NULL,

          payload        jsonb NOT NULL,          -- kwargs di canonical.write_evidence
          status         text NOT NULL DEFAULT 'pending'
                         CHECK (status IN ('pending','processing','done','failed')),
          attempts       int NOT NULL DEFAULT 0,
          last_error     text,
          result         jsonb,                  -- counts di write_evidence (audit)

          created_at     timestamptz NOT NULL DEFAULT now(),
          updated_at     timestamptz NOT NULL DEFAULT now(),
          processed_at   timestamptz
        );
        """
    )
    # 'processing' = presa in carico da un worker; un supervisore la rimette
    # 'pending' se resta appesa (worker morto).
    op.execute(
        "CREATE INDEX kg_ingest_queue_active ON kg_ingest_queue (id) "
        "WHERE status IN ('pending','processing');"
    )
    # niente trigger updated_at: qui `updated_at` = ultimo tocco del worker
    # (claim / esito), lo gestisce lui esplicitamente. Serve alla detection dei
    # 'processing' appesi, che un trigger set-now clobbererebbe.

    # RLS: pattern strict-client (come client/project/process). Con contesto
    # solo-consultant il drain vede tutte le righe del consulente.
    pred = (
        "consultant_id = app_consultant_id() "
        "AND (app_client_id() IS NULL OR client_id = app_client_id())"
    )
    op.execute("ALTER TABLE kg_ingest_queue ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE kg_ingest_queue FORCE ROW LEVEL SECURITY;")
    op.execute(
        f"CREATE POLICY kg_ingest_queue_tenant ON kg_ingest_queue "
        f"USING ({pred}) WITH CHECK ({pred});"
    )

    # delir_app: accoda (tool) e drena (ingest_worker gira come delir_app perche'
    # deve poi eseguire la DML di dominio di write_evidence).
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON kg_ingest_queue TO delir_app;"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS kg_ingest_queue CASCADE;")
