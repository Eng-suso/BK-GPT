"""Fix review: dedup di kg_entity/kg_relation su indice unique PARZIALE

Revision ID: 0008_dedup_partial_indexes
Revises: 0007_workspace_bridge
Create Date: 2026-09-01

Il dedup di kg_entity (0006, UNIQUE constraint) e kg_relation (0007, UNIQUE
index) includeva `client_id` nullable: due righe consultant-scoped
(client_id NULL) con gli stessi altri campi NON collidono (NULL <> NULL in
UNIQUE) -> ON CONFLICT non deduplicava per lo scope consultant.

Si passa a indici unique PARZIALI `WHERE client_id IS NOT NULL`: il dedup
copre lo scope client (l'unico scritto oggi). Per lo scope consultant il
dedup arrivera' col learning flow (P7), con la sua chiave.
"""

from __future__ import annotations

from alembic import op

revision = "0008_dedup_partial_indexes"
down_revision = "0007_workspace_bridge"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE cname text;
        BEGIN
          SELECT conname INTO cname FROM pg_constraint
          WHERE conrelid = 'kg_entity'::regclass AND contype = 'u';
          IF cname IS NOT NULL THEN
            EXECUTE format('ALTER TABLE kg_entity DROP CONSTRAINT %I', cname);
          END IF;
        END $$;
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX kg_entity_dedup ON kg_entity "
        "(consultant_id, client_id, entity_type, canonical_name) "
        "WHERE client_id IS NOT NULL;"
    )

    op.execute("DROP INDEX IF EXISTS kg_relation_triple;")
    op.execute(
        "CREATE UNIQUE INDEX kg_relation_dedup ON kg_relation "
        "(consultant_id, client_id, source_entity_id, target_entity_id, relation) "
        "WHERE client_id IS NOT NULL;"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS kg_relation_dedup;")
    op.execute(
        "CREATE UNIQUE INDEX kg_relation_triple ON kg_relation "
        "(consultant_id, client_id, source_entity_id, target_entity_id, relation);"
    )
    op.execute("DROP INDEX IF EXISTS kg_entity_dedup;")
    op.execute(
        "ALTER TABLE kg_entity ADD CONSTRAINT kg_entity_dedup_uq "
        "UNIQUE (consultant_id, client_id, entity_type, canonical_name);"
    )
