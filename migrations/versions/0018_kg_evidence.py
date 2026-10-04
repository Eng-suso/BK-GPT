"""Le affermazioni dei file caricati nel grafo: Source -> Evidence -> Claim

Revision ID: 0018_kg_evidence
Revises: 0017_queue_backoff
Create Date: 2026-10-03

P1.14 del piano. Un file caricato nel workspace produce affermazioni ancorate
a una porzione (P1.12). Fin qui restavano nel database workspace: il grafo non
sapeva da quale file e da quale pagina venisse un'affermazione.

- `kg_source` diventa un nodo (`Source`): prende `layer` / `status` /
  `confidence` come le altre tabelle proiettate, e `workspace_source_id`, la
  fonte del workspace da cui viene. Due fonti workspace con lo stesso file
  (stesso cliente, processi diversi) sono due fonti: l'unicita' per contenuto
  vale solo per le fonti che non vengono da un file del workspace.
- `kg_evidence` (nodo `Evidence`): la porzione citata, con la sua ancora
  ("p.3", "§2", "R4"). Il testo resta nel workspace: qui c'e' solo dove sta.
- `kg_claim.evidence_id`: la porzione che sostiene l'affermazione, da cui
  l'arco `Evidence -SUPPORTS-> Claim`. Cancellare la porzione cancella
  l'affermazione: un'affermazione senza ancora non esiste.
"""

from __future__ import annotations

from alembic import op

revision = "0018_kg_evidence"
down_revision = "0017_queue_backoff"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE kg_source
          ADD COLUMN IF NOT EXISTS layer text NOT NULL DEFAULT 'L1'
            CHECK (layer IN ('L1','L2','L3')),
          ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'active'
            CHECK (status IN ('candidate','active','deprecated','rejected')),
          ADD COLUMN IF NOT EXISTS confidence real NOT NULL DEFAULT 1.0
            CHECK (confidence BETWEEN 0 AND 1),
          ADD COLUMN IF NOT EXISTS workspace_source_id text;
        """
    )
    # L'unicita' per contenuto resta per le fonti nate da testo (chat, note):
    # un file del workspace e' identificato dalla sua fonte workspace.
    op.execute("DROP INDEX IF EXISTS kg_source_client_content_hash;")
    op.execute(
        "CREATE UNIQUE INDEX kg_source_client_content_hash ON kg_source "
        "(consultant_id, client_id, content_hash) "
        "WHERE client_id IS NOT NULL AND workspace_source_id IS NULL;"
    )
    op.execute(
        "CREATE UNIQUE INDEX kg_source_workspace_source ON kg_source "
        "(consultant_id, client_id, workspace_source_id) WHERE workspace_source_id IS NOT NULL;"
    )

    op.execute(
        """
        CREATE TABLE kg_evidence (
          id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          source_id     uuid NOT NULL REFERENCES kg_source(id) ON DELETE CASCADE,
          consultant_id uuid NOT NULL REFERENCES consultant(id) ON DELETE CASCADE,
          client_id     uuid NOT NULL REFERENCES client(id)  ON DELETE CASCADE,
          project_id    uuid REFERENCES project(id) ON DELETE CASCADE,
          process_id    uuid REFERENCES process(id) ON DELETE SET NULL,
          layer         text NOT NULL DEFAULT 'L1' CHECK (layer IN ('L1','L2','L3')),
          status        text NOT NULL DEFAULT 'active'
                        CHECK (status IN ('candidate','active','deprecated','rejected')),
          confidence    real NOT NULL DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),
          ordinal       int  NOT NULL,
          anchor        text NOT NULL,
          locator       jsonb NOT NULL DEFAULT '{}',
          created_at    timestamptz NOT NULL DEFAULT now(),
          UNIQUE (source_id, ordinal)
        );
        """
    )
    op.execute(
        "CREATE INDEX kg_evidence_scope ON kg_evidence (consultant_id, client_id, project_id);"
    )
    pred = "consultant_id = app_consultant_id() AND client_id = app_client_id()"
    op.execute("ALTER TABLE kg_evidence ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE kg_evidence FORCE ROW LEVEL SECURITY;")
    op.execute(
        f"CREATE POLICY kg_evidence_tenant ON kg_evidence USING ({pred}) WITH CHECK ({pred});"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON kg_evidence TO delir_app;")

    op.execute(
        "ALTER TABLE kg_claim ADD COLUMN IF NOT EXISTS evidence_id uuid "
        "REFERENCES kg_evidence(id) ON DELETE CASCADE;"
    )
    op.execute(
        "CREATE INDEX kg_claim_evidence ON kg_claim (evidence_id) WHERE evidence_id IS NOT NULL;"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS kg_claim_evidence;")
    op.execute("ALTER TABLE kg_claim DROP COLUMN IF EXISTS evidence_id;")
    op.execute("DROP TABLE IF EXISTS kg_evidence;")
    op.execute("DROP INDEX IF EXISTS kg_source_workspace_source;")
    # Le fonti dei file workspace possono condividere il contenuto: senza la
    # loro colonna l'indice di prima non si ricostruirebbe.
    op.execute("DELETE FROM kg_source WHERE workspace_source_id IS NOT NULL;")
    op.execute("DROP INDEX IF EXISTS kg_source_client_content_hash;")
    op.execute(
        "CREATE UNIQUE INDEX kg_source_client_content_hash ON kg_source "
        "(consultant_id, client_id, content_hash) WHERE client_id IS NOT NULL;"
    )
    op.execute(
        "ALTER TABLE kg_source DROP COLUMN IF EXISTS workspace_source_id, "
        "DROP COLUMN IF EXISTS confidence, DROP COLUMN IF EXISTS status, "
        "DROP COLUMN IF EXISTS layer;"
    )
