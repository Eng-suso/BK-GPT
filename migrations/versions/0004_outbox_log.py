"""graph_outbox + mem0_projection_log + grant worker

Revision ID: 0004_outbox_log
Revises: 0003_memory_tables
Create Date: 2026-09-01

Copre: INV-7 (transactional outbox), parte di INV-2 / INV-10.

Due code. Il payload e' materializzato nella stessa transazione della scrittura
di dominio, quindi il worker non rilegge mai le tabelle di dominio -> niente RLS
su queste due.

Privilegi (correzione: delir_app NON deve avere SELECT indiscriminato):
- delir_app  -> solo INSERT (accoda)
- delir_worker -> SELECT + UPDATE (drena)
- debug/status per l'app -> via la view v_projection_backlog, scoped per
  consultant, che gira con i privilegi dell'owner (delir_migrator).
"""

from __future__ import annotations

from alembic import op

revision = "0004_outbox_log"
down_revision = "0003_memory_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE graph_outbox (
          id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          aggregate_type text NOT NULL,
          aggregate_id   uuid NOT NULL,
          consultant_id  uuid NOT NULL,
          client_id      uuid,
          op             text NOT NULL CHECK (op IN ('upsert','delete')),
          payload        jsonb NOT NULL,
          dedupe_key     text NOT NULL UNIQUE,
          created_at     timestamptz NOT NULL DEFAULT now(),
          processed_at   timestamptz,
          attempts       int NOT NULL DEFAULT 0,
          last_error     text
        );
        """
    )
    op.execute(
        "CREATE INDEX graph_outbox_pending ON graph_outbox (id) "
        "WHERE processed_at IS NULL;"
    )

    op.execute(
        """
        CREATE TABLE mem0_projection_log (
          id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          memory_kind    text NOT NULL CHECK (memory_kind IN ('semantic','episodic','procedural')),
          memory_id      uuid NOT NULL,
          consultant_id  uuid NOT NULL,
          client_id      uuid,
          op             text NOT NULL CHECK (op IN ('add','update','delete')),
          mem0_payload   jsonb NOT NULL,
          mem0_memory_id text,
          source_ids     uuid[] NOT NULL DEFAULT '{}',
          created_at     timestamptz NOT NULL DEFAULT now(),
          applied_at     timestamptz,
          attempts       int NOT NULL DEFAULT 0,
          last_error     text
        );
        """
    )
    op.execute(
        "CREATE INDEX mem0_log_pending ON mem0_projection_log (id) "
        "WHERE applied_at IS NULL;"
    )

    # le default privileges della 0001 hanno gia' dato DML pieno a delir_app:
    # su queste due lo restringiamo a solo INSERT.
    op.execute("REVOKE ALL ON graph_outbox, mem0_projection_log FROM delir_app;")
    op.execute("GRANT INSERT ON graph_outbox, mem0_projection_log TO delir_app;")
    op.execute(
        "GRANT SELECT, UPDATE ON graph_outbox, mem0_projection_log TO delir_worker;"
    )

    op.execute(
        """
        CREATE VIEW v_projection_backlog AS
        SELECT 'graph_outbox'::text AS queue,
               consultant_id,
               client_id,
               count(*) FILTER (WHERE processed_at IS NULL) AS pending,
               count(*) FILTER (WHERE last_error IS NOT NULL AND processed_at IS NULL) AS failing,
               max(created_at) AS newest
        FROM graph_outbox
        WHERE consultant_id = app_consultant_id()
        GROUP BY consultant_id, client_id
        UNION ALL
        SELECT 'mem0_projection_log'::text,
               consultant_id,
               client_id,
               count(*) FILTER (WHERE applied_at IS NULL),
               count(*) FILTER (WHERE last_error IS NOT NULL AND applied_at IS NULL),
               max(created_at)
        FROM mem0_projection_log
        WHERE consultant_id = app_consultant_id()
        GROUP BY consultant_id, client_id;
        """
    )
    op.execute("GRANT SELECT ON v_projection_backlog TO delir_app;")


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_projection_backlog;")
    op.execute("DROP TABLE IF EXISTS mem0_projection_log CASCADE;")
    op.execute("DROP TABLE IF EXISTS graph_outbox CASCADE;")
