"""semantic_memory / episodic_memory / procedural_memory

Revision ID: 0003_memory_tables
Revises: 0002_sources_chunks
Create Date: 2026-09-01

Copre: INV-11 (tassonomia), INV-13 (due scope + lifecycle).

- scope client|consultant, vincolato a client_id via CHECK
- lifecycle: status / confidence / version / lineage_id / supersedes_id
- provenance: source_ids[] -> kg_source, derived_from[] -> episodic_memory
- guardrail_status + gate: una riga non puo' andare 'active' finche' il
  guardrail non e' 'clean' (promozione client->consultant reviewata)
- default status: 'active' per semantic (eligible for use, NON verified truth:
  confidence/provenance/contradiction restano separati), 'candidate' per
  procedural (un playbook appreso non entra nel runtime finche' non e' promosso)

updated_at via trigger set_updated_at() (creato in 0001).
"""

from __future__ import annotations

from alembic import op

revision = "0003_memory_tables"
down_revision = "0002_sources_chunks"
branch_labels = None
depends_on = None

_SCOPE_CHECK = """
  CONSTRAINT {name}_scope_client CHECK (
    (scope = 'client'     AND client_id IS NOT NULL) OR
    (scope = 'consultant' AND client_id IS NULL)
  )
"""

_GUARDRAIL_GATE = """
  CONSTRAINT {name}_guardrail_gate CHECK (
    status <> 'active' OR guardrail_status = 'clean'
  )
"""


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE semantic_memory (
          id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          consultant_id  uuid NOT NULL REFERENCES consultant(id) ON DELETE CASCADE,
          client_id      uuid REFERENCES client(id)  ON DELETE CASCADE,
          project_id     uuid REFERENCES project(id) ON DELETE CASCADE,
          process_id     uuid REFERENCES process(id) ON DELETE SET NULL,

          scope          text NOT NULL CHECK (scope IN ('client','consultant')),
          kind           text NOT NULL CHECK (kind IN
                           ('fact','preference','concept','rule','claim_summary')),
          statement      text NOT NULL,
          subject        text,
          category       text,

          status         text NOT NULL DEFAULT 'active'
                         CHECK (status IN ('candidate','active','deprecated','rejected')),
          confidence     real NOT NULL DEFAULT 0.5 CHECK (confidence BETWEEN 0 AND 1),
          version        int  NOT NULL DEFAULT 1,
          lineage_id     uuid NOT NULL DEFAULT gen_random_uuid(),
          supersedes_id  uuid REFERENCES semantic_memory(id) ON DELETE SET NULL,
          guardrail_status text NOT NULL DEFAULT 'clean'
                         CHECK (guardrail_status IN ('clean','pending','flagged')),

          source_ids     uuid[] NOT NULL DEFAULT '{{}}',
          derived_from   uuid[] NOT NULL DEFAULT '{{}}',

          created_by     text NOT NULL DEFAULT 'agent'
                         CHECK (created_by IN ('agent','consultant','migration')),
          created_at     timestamptz NOT NULL DEFAULT now(),
          updated_at     timestamptz NOT NULL DEFAULT now(),

          {_SCOPE_CHECK.format(name='semantic')},
          {_GUARDRAIL_GATE.format(name='semantic')}
        );
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX semantic_one_active ON semantic_memory (lineage_id) "
        "WHERE status = 'active';"
    )
    op.execute(
        "CREATE INDEX semantic_scope ON semantic_memory "
        "(consultant_id, client_id, project_id);"
    )
    op.execute(
        "CREATE INDEX semantic_lookup ON semantic_memory (scope, kind, status);"
    )
    op.execute(
        "CREATE TRIGGER t_semantic_updated BEFORE UPDATE ON semantic_memory "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
    )

    op.execute(
        f"""
        CREATE TABLE episodic_memory (
          id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          consultant_id  uuid NOT NULL REFERENCES consultant(id) ON DELETE CASCADE,
          client_id      uuid REFERENCES client(id)  ON DELETE CASCADE,
          project_id     uuid REFERENCES project(id) ON DELETE CASCADE,
          process_id     uuid REFERENCES process(id) ON DELETE SET NULL,

          scope          text NOT NULL CHECK (scope IN ('client','consultant')),
          episode_type   text NOT NULL CHECK (episode_type IN
                           ('interview','call','note','decision','workshop',
                            'feedback','observation','run')),
          title          text NOT NULL,
          summary        text,
          occurred_at    timestamptz,
          participants   text[] NOT NULL DEFAULT '{{}}',
          raw_source_id  uuid REFERENCES kg_source(id) ON DELETE SET NULL,

          status         text NOT NULL DEFAULT 'active'
                         CHECK (status IN ('active','archived','rejected')),
          confidence     real NOT NULL DEFAULT 0.5 CHECK (confidence BETWEEN 0 AND 1),
          source_ids     uuid[] NOT NULL DEFAULT '{{}}',

          created_by     text NOT NULL DEFAULT 'agent'
                         CHECK (created_by IN ('agent','consultant','migration')),
          created_at     timestamptz NOT NULL DEFAULT now(),
          updated_at     timestamptz NOT NULL DEFAULT now(),

          {_SCOPE_CHECK.format(name='episodic')}
        );
        """
    )
    op.execute(
        "CREATE INDEX episodic_scope ON episodic_memory "
        "(consultant_id, client_id, project_id);"
    )
    op.execute(
        "CREATE INDEX episodic_time ON episodic_memory "
        "(occurred_at DESC NULLS LAST);"
    )
    op.execute(
        "CREATE TRIGGER t_episodic_updated BEFORE UPDATE ON episodic_memory "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
    )

    op.execute(
        f"""
        CREATE TABLE procedural_memory (
          id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          consultant_id  uuid NOT NULL REFERENCES consultant(id) ON DELETE CASCADE,
          client_id      uuid REFERENCES client(id)  ON DELETE CASCADE,
          project_id     uuid REFERENCES project(id) ON DELETE SET NULL,

          scope          text NOT NULL CHECK (scope IN ('client','consultant')),
          kind           text NOT NULL CHECK (kind IN ('playbook','heuristic','checklist')),
          title          text NOT NULL,
          applies_when   text,
          body           text NOT NULL,

          status         text NOT NULL DEFAULT 'candidate'
                         CHECK (status IN ('candidate','active','deprecated','rejected')),
          confidence     real NOT NULL DEFAULT 0.5 CHECK (confidence BETWEEN 0 AND 1),
          version        int  NOT NULL DEFAULT 1,
          lineage_id     uuid NOT NULL DEFAULT gen_random_uuid(),
          supersedes_id  uuid REFERENCES procedural_memory(id) ON DELETE SET NULL,
          guardrail_status text NOT NULL DEFAULT 'clean'
                         CHECK (guardrail_status IN ('clean','pending','flagged')),

          source_ids     uuid[] NOT NULL DEFAULT '{{}}',
          derived_from   uuid[] NOT NULL DEFAULT '{{}}',

          created_by     text NOT NULL DEFAULT 'agent'
                         CHECK (created_by IN ('agent','consultant','migration')),
          created_at     timestamptz NOT NULL DEFAULT now(),
          updated_at     timestamptz NOT NULL DEFAULT now(),
          activated_at   timestamptz,

          {_SCOPE_CHECK.format(name='procedural')},
          {_GUARDRAIL_GATE.format(name='procedural')}
        );
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX procedural_one_active ON procedural_memory (lineage_id) "
        "WHERE status = 'active';"
    )
    op.execute(
        "CREATE INDEX procedural_scope ON procedural_memory (consultant_id, client_id);"
    )
    op.execute(
        "CREATE INDEX procedural_active ON procedural_memory (scope, status) "
        "WHERE status = 'active';"
    )
    op.execute(
        "CREATE TRIGGER t_procedural_updated BEFORE UPDATE ON procedural_memory "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
    )


def downgrade() -> None:
    for table in ("procedural_memory", "episodic_memory", "semantic_memory"):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
