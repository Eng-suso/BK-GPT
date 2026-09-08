"""Provenance per claim + tipo di divergenza sulle contraddizioni

Revision ID: 0015_claim_provenance
Revises: 0014_memory_lifecycle
Create Date: 2026-09-08

Difetti del test E2E V3: affermazioni attribuite alla persona sbagliata,
sovrapposizioni fra fonti dichiarate e mai verificate, richieste di audit
"claim -> fonte -> estratto" a cui si rispondeva con una nuova sintesi,
testimonianze di un reparto generalizzate al processo intero.

La causa comune e' qui, nello schema: `kg_claim` teneva solo `statement` +
`source_ids` (l'array delle fonti del *pacchetto* di evidenza, non della
singola affermazione). Chi parlava, con quali parole, per quale perimetro e
in che modo epistemico non veniva scritto da nessuna parte - il tool lo
chiedeva all'LLM (`KnowledgeGraphClaim.source_name`) e il write path lo
buttava via. Da li' in poi ogni attribuzione era una ricostruzione a valle.

Colonne aggiunte a `kg_claim`:
  - `attributed_to`   chi lo dice dentro la fonte (una fonte, piu' voci);
  - `source_name`     nome della fonte come dichiarato dall'estrazione;
  - `topic`           chiave del tema: la corroborazione si conta su questa;
  - `quote`           passaggio verbatim che regge il claim;
  - `quote_verified`  la citazione e' stata riscontrata nel testo sorgente;
  - `scope_label`     reparto/ruolo/contesto a cui il claim si riferisce;
  - `scope_level`     stated_scope | whole_process;
  - `epistemic_status` reported | observed | documented | inferred | declared_unknown.

E a `kg_contradiction`:
  - `divergence_type` che tipo di disaccordo e' davvero.

Tutte NOT NULL con default: le righe esistenti restano valide e si presentano
per quello che sono - evidenza senza provenance verificabile
(`quote_verified=false`, `attributed_to=''`).

INV-5 / B+: i campi testuali (`attributed_to`, `source_name`, `quote`,
`scope_label`, `topic`) restano solo in Postgres. Verso Neo4j passano gli
enum non identificativi (`scope_level`, `epistemic_status`, `quote_verified`,
`divergence_type`) - vedi `backend/memory/knowledge_graph/catalog.py`.
"""

from __future__ import annotations

from alembic import op

revision = "0015_claim_provenance"
down_revision = "0014_memory_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add per-claim provenance columns and the divergence type on contradictions."""
    op.execute(
        """
        ALTER TABLE kg_claim
          ADD COLUMN attributed_to    text    NOT NULL DEFAULT '',
          ADD COLUMN source_name      text    NOT NULL DEFAULT '',
          ADD COLUMN topic            text    NOT NULL DEFAULT '',
          ADD COLUMN quote            text    NOT NULL DEFAULT '',
          ADD COLUMN quote_verified   boolean NOT NULL DEFAULT false,
          ADD COLUMN scope_label      text    NOT NULL DEFAULT '',
          ADD COLUMN scope_level      text    NOT NULL DEFAULT 'stated_scope'
            CHECK (scope_level IN ('stated_scope','whole_process')),
          ADD COLUMN epistemic_status text    NOT NULL DEFAULT 'reported'
            CHECK (epistemic_status IN
              ('reported','observed','documented','inferred','declared_unknown'));
        """
    )
    # Il registro dell'evidenza di un processo si legge per processo + tema:
    # e' la query dell'audit di provenance e del ledger che apre ogni chat.
    op.execute(
        "CREATE INDEX kg_claim_process_topic ON kg_claim (process_id, topic) "
        "WHERE process_id IS NOT NULL;"
    )
    op.execute(
        """
        ALTER TABLE kg_contradiction
          ADD COLUMN divergence_type text NOT NULL DEFAULT 'incompatible'
            CHECK (divergence_type IN
              ('incompatible','scope_difference','formalization_difference',
               'knowledge_gap','complementary','tension_to_explore',
               'single_source_uncertainty'));
        """
    )


def downgrade() -> None:
    """Drop the provenance columns and the divergence type."""
    op.execute("DROP INDEX IF EXISTS kg_claim_process_topic;")
    op.execute(
        """
        ALTER TABLE kg_claim
          DROP COLUMN IF EXISTS attributed_to,
          DROP COLUMN IF EXISTS source_name,
          DROP COLUMN IF EXISTS topic,
          DROP COLUMN IF EXISTS quote,
          DROP COLUMN IF EXISTS quote_verified,
          DROP COLUMN IF EXISTS scope_label,
          DROP COLUMN IF EXISTS scope_level,
          DROP COLUMN IF EXISTS epistemic_status;
        """
    )
    op.execute("ALTER TABLE kg_contradiction DROP COLUMN IF EXISTS divergence_type;")
