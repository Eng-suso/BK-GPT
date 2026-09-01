"""kg_source (provenance) + kg_chunk (indice vettoriale KG)

Revision ID: 0002_sources_chunks
Revises: 0001_backbone
Create Date: 2026-09-01

Copre: INV-4 (embedding contract), parte di INV-1 / INV-10.
- kg_source: registro di provenance, un record per sorgente ingerita
- kg_chunk: indice vettoriale KG separato logicamente dal vector store di Mem0
  (D2). vector(1536) tipizzato + HNSW + tsvector full-text di fallback.

delir_app riceve la DML su queste tabelle dalle default privileges della 0001.
"""

from __future__ import annotations

from alembic import op

revision = "0002_sources_chunks"
down_revision = "0001_backbone"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE kg_source (
          id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          consultant_id uuid NOT NULL REFERENCES consultant(id) ON DELETE CASCADE,
          client_id     uuid REFERENCES client(id)  ON DELETE CASCADE,
          project_id    uuid REFERENCES project(id) ON DELETE CASCADE,
          process_id    uuid REFERENCES process(id) ON DELETE SET NULL,

          scope         text NOT NULL CHECK (scope IN ('client','consultant')),
          kind          text NOT NULL CHECK (kind IN (
                          'interview_transcript','document','chat_extract',
                          'system_export','note','observation')),
          title         text NOT NULL,
          blob_uri      text,
          content_hash  text NOT NULL,
          byte_size     bigint,
          ingested_at   timestamptz NOT NULL DEFAULT now(),

          CONSTRAINT kg_source_scope_client CHECK (
            (scope = 'client'     AND client_id IS NOT NULL) OR
            (scope = 'consultant' AND client_id IS NULL)
          ),
          UNIQUE (consultant_id, content_hash)
        );
        """
    )
    op.execute(
        "CREATE INDEX kg_source_scope ON kg_source (consultant_id, client_id, project_id);"
    )

    op.execute(
        """
        CREATE TABLE kg_chunk (
          id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          source_id     uuid NOT NULL REFERENCES kg_source(id) ON DELETE CASCADE,
          consultant_id uuid NOT NULL REFERENCES consultant(id) ON DELETE CASCADE,
          client_id     uuid REFERENCES client(id)  ON DELETE CASCADE,
          project_id    uuid REFERENCES project(id) ON DELETE CASCADE,

          ordinal       int  NOT NULL,
          content       text NOT NULL,
          content_tsv   tsvector GENERATED ALWAYS AS
                          (to_tsvector('simple', content)) STORED,

          embedding     vector(1536),
          embed_model   text,
          embed_dim     int,
          embed_version int,
          created_at    timestamptz NOT NULL DEFAULT now(),
          embedded_at   timestamptz,

          CONSTRAINT kg_chunk_embed_dim CHECK (embed_dim IS NULL OR embed_dim = 1536),
          UNIQUE (source_id, ordinal)
        );
        """
    )
    op.execute(
        "CREATE INDEX kg_chunk_hnsw ON kg_chunk "
        "USING hnsw (embedding vector_cosine_ops);"
    )
    op.execute("CREATE INDEX kg_chunk_tsv ON kg_chunk USING gin (content_tsv);")
    op.execute(
        "CREATE INDEX kg_chunk_scope ON kg_chunk (consultant_id, client_id, project_id);"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS kg_chunk CASCADE;")
    op.execute("DROP TABLE IF EXISTS kg_source CASCADE;")
