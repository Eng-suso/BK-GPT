"""Lo stato della proiezione Neo4j per cliente: fin dove e' arrivata, chi l'ha scritta, se e' guasta

Revision ID: 0019_graph_projection_state
Revises: 0018_kg_evidence
Create Date: 2026-10-07

P1.1b del piano backend. `ProjectionHealth` (#56) deduceva lo stato del grafo
dalla sola coda: dead-letter, righe bloccate, eta' della pendente piu' vecchia.
Tre cose non le poteva vedere:

- **fin dove** il grafo di un cliente e' arrivato. La retention cancella le
  righe gia' proiettate, e con loro la memoria del punto raggiunto. `watermark`
  e' l'id piu' alto di `graph_outbox` applicato per quel cliente: lo avanza il
  worker, nella stessa transazione in cui segna la riga come processata;
- **chi** l'ha scritto. Un grafo proiettato da un projector di forma diversa
  e' un grafo con nodi di due forme. `projector_version` e' la versione piu'
  vecchia che ha scritto il grafo di quel cliente: la nuova versione non la
  sovrascrive, solo una ricostruzione completa (`kg_reproject --apply`) la
  porta avanti;
- **se e' guasto**. La riconciliazione (`kg_reproject`) confronta il grafo con
  Postgres; una differenza non e' un ritardo della coda, e' un grafo che dice
  il falso. `corrupt_since` / `corrupt_reason` lo ricordano finche' un
  confronto pulito non lo smentisce.

Niente RLS, come le code: la legge il gateway con la DSN del worker, la scrive
il worker (watermark) e lo script di riconciliazione come delir_migrator.
"""

from __future__ import annotations

from alembic import op

revision = "0019_graph_projection_state"
down_revision = "0018_kg_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE graph_projection_state (
          client_id         uuid PRIMARY KEY,
          watermark         bigint NOT NULL DEFAULT 0 CHECK (watermark >= 0),
          projector_version text NOT NULL,
          corrupt_since     timestamptz,
          corrupt_reason    text,
          verified_at       timestamptz,
          updated_at        timestamptz NOT NULL DEFAULT now(),
          CHECK ((corrupt_since IS NULL) = (corrupt_reason IS NULL))
        );
        """
    )
    op.execute("REVOKE ALL ON graph_projection_state FROM delir_app;")
    op.execute("GRANT SELECT, INSERT, UPDATE ON graph_projection_state TO delir_worker;")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS graph_projection_state;")
