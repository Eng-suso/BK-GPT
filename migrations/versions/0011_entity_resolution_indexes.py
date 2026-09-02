"""Entity resolution (P2) — indici per il match di kg_entity

Revision ID: 0011_entity_resolution_indexes
Revises: 0010_procedural_feedback
Create Date: 2026-09-02

Il dedup di kg_entity oggi e' solo per `canonical_name` esatto (0008). "CFO",
"direttore finanziario", "Chief Financial Officer" restano tre entita'. P2
aggiunge un resolver che, prima di inserire, cerca un'entita' gia' nota che sia
la stessa cosa del mondo reale:

  1. match esatto su `canonical_name` o su un elemento di `aliases`
     (case-insensitive, whitespace normalizzato);
  2. similarita' trigram sul nome (`pg_trgm`);
  3. similarita' coseno sull'embedding del nome (`kg_entity.embedding`, finora
     mai popolato);
  4. per la fascia incerta, un giudizio LLM.

Questa migration prepara solo gli indici. La colonna `embedding vector(1536)` +
il CHECK sulla dimensione esistono gia' dalla 0006.

- `kg_entity_embedding_hnsw` — HNSW coseno, PARZIALE su `embedding IS NOT NULL`
  (la maggior parte delle righe nasce senza embedding: backfill via
  `scripts/kg_resolve_entities.py`).
- `kg_entity_name_trgm` — GIN trigram su `lower(canonical_name)` per il
  candidato lessicale.
- `kg_entity_aliases_gin` — GIN su `aliases` per il match esatto sull'alias
  (`aliases @> ARRAY[...]`). Gli alias sono normalizzati lowercase in scrittura.
"""

from __future__ import annotations

from alembic import op

revision = "0011_entity_resolution_indexes"
down_revision = "0010_procedural_feedback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX kg_entity_embedding_hnsw ON kg_entity "
        "USING hnsw (embedding vector_cosine_ops) "
        "WHERE embedding IS NOT NULL;"
    )
    op.execute(
        "CREATE INDEX kg_entity_name_trgm ON kg_entity "
        "USING gin (lower(canonical_name) gin_trgm_ops);"
    )
    op.execute(
        "CREATE INDEX kg_entity_aliases_gin ON kg_entity USING gin (aliases);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS kg_entity_aliases_gin;")
    op.execute("DROP INDEX IF EXISTS kg_entity_name_trgm;")
    op.execute("DROP INDEX IF EXISTS kg_entity_embedding_hnsw;")
