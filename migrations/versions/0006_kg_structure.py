"""Catalogo struttura KG L1 — kg_entity / relation / claim / gap / contradiction / impact

Revision ID: 0006_kg_structure
Revises: 0005_rls_policies
Create Date: 2026-09-01

P0.5. Le tabelle Postgres che tengono la struttura estratta dall'evidenza
(INV-1). Il projector (P1) le legge e le proietta su Neo4j secondo
backend/memory/knowledge_graph/catalog.py, rispettando INV-5 (B+): il
`canonical_name` di kg_entity e i testi lunghi restano solo qui.

Colonne condivise (come le memory table della 0003, senza guardrail):
scope client|consultant, lifecycle status/confidence/lineage_id/supersedes_id,
provenance source_ids[]. RLS con il pattern "client_id nullable".
"""

from __future__ import annotations

from alembic import op

revision = "0006_kg_structure"
down_revision = "0005_rls_policies"
branch_labels = None
depends_on = None

_TABLES = ("kg_entity", "kg_relation", "kg_claim", "kg_gap", "kg_contradiction", "kg_impact")

_COMMON = """
  consultant_id  uuid NOT NULL REFERENCES consultant(id) ON DELETE CASCADE,
  client_id      uuid REFERENCES client(id)  ON DELETE CASCADE,
  project_id     uuid REFERENCES project(id) ON DELETE CASCADE,
  process_id     uuid REFERENCES process(id) ON DELETE SET NULL,
  scope          text NOT NULL DEFAULT 'client' CHECK (scope IN ('client','consultant')),
  layer          text NOT NULL DEFAULT 'L1' CHECK (layer IN ('L1','L2','L3')),
  status         text NOT NULL DEFAULT 'active'
                 CHECK (status IN ('candidate','active','deprecated','rejected')),
  confidence     real NOT NULL DEFAULT 0.5 CHECK (confidence BETWEEN 0 AND 1),
  lineage_id     uuid NOT NULL DEFAULT gen_random_uuid(),
  source_ids     uuid[] NOT NULL DEFAULT '{}',
  created_by     text NOT NULL DEFAULT 'agent'
                 CHECK (created_by IN ('agent','consultant','migration')),
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now()
"""


def _scope_check(name: str) -> str:
    return (
        f"CONSTRAINT {name}_scope_client CHECK ("
        "(scope = 'client' AND client_id IS NOT NULL) OR "
        "(scope = 'consultant' AND client_id IS NULL))"
    )


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE kg_entity (
          id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        {_COMMON},
          supersedes_id  uuid REFERENCES kg_entity(id) ON DELETE SET NULL,
          entity_type    text NOT NULL CHECK (entity_type IN
                           ('person','role','org_unit','system','activity','decision',
                            'handoff','document','data_object','policy','kpi','other')),
          canonical_name text NOT NULL,       -- SOLO Postgres, mai in Neo4j (B+)
          aliases        text[] NOT NULL DEFAULT '{{}}',
          attributes     jsonb  NOT NULL DEFAULT '{{}}',  -- role_type/department_type/... (whitelist)
          embedding      vector(1536),        -- entity resolution (P2)
          embed_model    text,
          embed_dim      int,
          embed_version  int,
          {_scope_check('kg_entity')},
          CONSTRAINT kg_entity_embed_dim CHECK (embed_dim IS NULL OR embed_dim = 1536),
          UNIQUE (consultant_id, client_id, entity_type, canonical_name)
        );
        """
    )

    op.execute(
        f"""
        CREATE TABLE kg_relation (
          id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        {_COMMON},
          supersedes_id    uuid REFERENCES kg_relation(id) ON DELETE SET NULL,
          source_entity_id uuid NOT NULL REFERENCES kg_entity(id) ON DELETE CASCADE,
          target_entity_id uuid NOT NULL REFERENCES kg_entity(id) ON DELETE CASCADE,
          relation         text NOT NULL,     -- label tipizzata: DEPENDS_ON, PERFORMS, USES, ...
          evidence         text NOT NULL DEFAULT '',
          confirmed        boolean NOT NULL DEFAULT false,
          {_scope_check('kg_relation')},
          CONSTRAINT kg_relation_not_self CHECK (source_entity_id <> target_entity_id)
        );
        """
    )

    op.execute(
        f"""
        CREATE TABLE kg_claim (
          id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        {_COMMON},
          supersedes_id       uuid REFERENCES kg_claim(id) ON DELETE SET NULL,
          statement           text NOT NULL,   -- astratto, B+ safe
          process_area        text NOT NULL CHECK (process_area IN
                                ('scope','actor','activity','decision','handoff','system',
                                 'data','exception','control','timing','other')),
          claim_status        text NOT NULL DEFAULT 'partial' CHECK (claim_status IN
                                ('confirmed','partial','contradicted','inferred','unsupported')),
          linked_element_hint text,
          {_scope_check('kg_claim')}
        );
        """
    )

    op.execute(
        f"""
        CREATE TABLE kg_gap (
          id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        {_COMMON},
          supersedes_id        uuid REFERENCES kg_gap(id) ON DELETE SET NULL,
          title                text NOT NULL,
          missing_information  text NOT NULL,
          required_evidence    text NOT NULL DEFAULT '',
          severity             text NOT NULL DEFAULT 'medium' CHECK (severity IN
                                 ('low','medium','high','critical','blocking')),
          affected_process_ids uuid[] NOT NULL DEFAULT '{{}}',
          resolved_at          timestamptz,
          {_scope_check('kg_gap')}
        );
        """
    )

    op.execute(
        f"""
        CREATE TABLE kg_contradiction (
          id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        {_COMMON},
          supersedes_id         uuid REFERENCES kg_contradiction(id) ON DELETE SET NULL,
          title                 text NOT NULL,
          conflicting_claim_ids uuid[] NOT NULL DEFAULT '{{}}',
          conflicting_statements text[] NOT NULL DEFAULT '{{}}',
          resolution_question   text NOT NULL DEFAULT '',
          severity              text NOT NULL DEFAULT 'medium' CHECK (severity IN
                                  ('low','medium','high','critical','blocking')),
          affected_process_ids  uuid[] NOT NULL DEFAULT '{{}}',
          resolution            text,
          resolved_at           timestamptz,
          {_scope_check('kg_contradiction')}
        );
        """
    )

    op.execute(
        f"""
        CREATE TABLE kg_impact (
          id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        {_COMMON},
          supersedes_id        uuid REFERENCES kg_impact(id) ON DELETE SET NULL,
          title                text NOT NULL,
          impact_area          text NOT NULL CHECK (impact_area IN
                                 ('cost','revenue','working_capital','risk','quality',
                                  'time','compliance','efficiency','roi')),
          mechanism            text NOT NULL,
          evidence             text NOT NULL DEFAULT '',
          affected_process_ids uuid[] NOT NULL DEFAULT '{{}}',
          {_scope_check('kg_impact')}
        );
        """
    )

    # indici di scope + trigger updated_at + RLS (pattern client_id nullable)
    pred = (
        "consultant_id = app_consultant_id() "
        "AND (client_id IS NULL OR client_id = app_client_id())"
    )
    for table in _TABLES:
        op.execute(
            f"CREATE INDEX {table}_scope ON {table} (consultant_id, client_id, project_id);"
        )
        op.execute(
            f"CREATE TRIGGER t_{table}_updated BEFORE UPDATE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
        )
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        op.execute(
            f"CREATE POLICY {table}_tenant ON {table} "
            f"USING ({pred}) WITH CHECK ({pred});"
        )

    op.execute("CREATE INDEX kg_entity_lineage ON kg_entity (lineage_id);")
    op.execute(
        "CREATE INDEX kg_relation_endpoints ON kg_relation "
        "(source_entity_id, target_entity_id);"
    )
    op.execute("CREATE INDEX kg_claim_process ON kg_claim (process_id) WHERE process_id IS NOT NULL;")


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
