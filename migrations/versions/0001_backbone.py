"""backbone tenancy + funzioni di contesto RLS

Revision ID: 0001_backbone
Revises:
Create Date: 2026-09-01

Copre: parte di INV-1 / INV-6 / INV-10.
- funzioni app_consultant_id() / app_client_id() lette dalle policy RLS
- funzione set_updated_at() per i trigger delle memory table (0003)
- gerarchia consultant -> client -> project -> process con ON DELETE CASCADE
- grant DML a delir_app + default privileges per le tabelle future

I ruoli delir_migrator / delir_app / delir_worker e le estensioni (vector,
pg_trgm) li crea il bootstrap superuser (ops/postgres/init/00-bootstrap.sh),
non questa migration: delir_migrator ha NOCREATEROLE.
"""

from __future__ import annotations

from alembic import op

revision = "0001_backbone"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION app_consultant_id() RETURNS uuid
        LANGUAGE sql STABLE AS $$
          SELECT nullif(current_setting('app.current_consultant_id', true), '')::uuid
        $$;
        """
    )
    op.execute(
        """
        CREATE FUNCTION app_client_id() RETURNS uuid
        LANGUAGE sql STABLE AS $$
          SELECT nullif(current_setting('app.current_client_id', true), '')::uuid
        $$;
        """
    )
    op.execute(
        """
        CREATE FUNCTION set_updated_at() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          NEW.updated_at := now();
          RETURN NEW;
        END
        $$;
        """
    )

    op.execute(
        """
        CREATE TABLE consultant (
          id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          email        text NOT NULL UNIQUE,
          display_name text NOT NULL,
          created_at   timestamptz NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        """
        CREATE TABLE client (
          id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          consultant_id uuid NOT NULL REFERENCES consultant(id) ON DELETE CASCADE,
          name          text NOT NULL,
          status        text NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active','archived','offboarded')),
          created_at    timestamptz NOT NULL DEFAULT now(),
          UNIQUE (consultant_id, name)
        );
        """
    )
    op.execute(
        """
        CREATE TABLE project (
          id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          client_id     uuid NOT NULL REFERENCES client(id) ON DELETE CASCADE,
          consultant_id uuid NOT NULL REFERENCES consultant(id) ON DELETE CASCADE,
          name          text NOT NULL,
          created_at    timestamptz NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        """
        CREATE TABLE process (
          id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          project_id    uuid NOT NULL REFERENCES project(id) ON DELETE CASCADE,
          client_id     uuid NOT NULL REFERENCES client(id) ON DELETE CASCADE,
          consultant_id uuid NOT NULL REFERENCES consultant(id) ON DELETE CASCADE,
          name          text NOT NULL,
          created_at    timestamptz NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX client_by_consultant ON client (consultant_id);")
    op.execute("CREATE INDEX project_by_client ON project (client_id, consultant_id);")
    op.execute("CREATE INDEX process_by_project ON process (project_id, consultant_id);")

    # DML a delir_app sulle tabelle attuali + default per le prossime migration.
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO delir_app;"
    )
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO delir_app;")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO delir_app;"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT USAGE, SELECT ON SEQUENCES TO delir_app;"
    )


def downgrade() -> None:
    for table in ("process", "project", "client", "consultant"):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
    for fn in ("set_updated_at()", "app_client_id()", "app_consultant_id()"):
        op.execute(f"DROP FUNCTION IF EXISTS {fn};")
