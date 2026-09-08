"""Proposizione e attributi del claim: la corroborazione smette di essere per soggetto

Revision ID: 0016_claim_assertion_qualifiers
Revises: 0015_claim_provenance
Create Date: 2026-09-08

Follow-up V3. Con la 0015 la provenance del singolo claim arriva fino in
fondo, ma la corroborazione si contava su `topic` — il **soggetto**. Due fonti
che parlano di autorizzazione venivano dichiarate concordi sull'autorizzazione,
e la sintesi ne scriveva una frase sola attribuita a entrambe, ereditando
proprieta' che ne aveva detta una: "Acquisti verifica l'autorizzazione prima
dell'ordine" attribuito anche a chi dichiarava di non conoscere la policy,
"fornitore gia' conosciuto" attribuito anche a chi aveva parlato solo di
contatto diretto.

Due colonne separano cio' che stava insieme:

  - `assertion`  la **proposizione**: e' su questa che si conta la
                 corroborazione. Senza, si ricade sull'enunciato, quindi due
                 formulazioni diverse restano due affermazioni diverse (fail
                 closed: meglio due `single_source` che un accordo inventato);
  - `qualifiers` gli attributi che QUELLA fonte aggiunge. Un attributo
                 dichiarato da una sola voce non puo' comparire in una frase
                 attribuita a piu' voci — il controllo e' deterministico
                 proprio perche' gli attributi sono dichiarati, non dedotti dal
                 testo a valle.

`topic` resta: e' il soggetto, serve a navigare e a mettere vicino cio' che
parla della stessa cosa. Non e' piu' la chiave dell'accordo.

INV-5 / B+: entrambe sono testo dell'evidenza e restano solo in Postgres.
"""

from __future__ import annotations

from alembic import op

revision = "0016_claim_assertion_qualifiers"
down_revision = "0015_claim_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the proposition key and the per-source qualifiers to kg_claim."""
    op.execute(
        """
        ALTER TABLE kg_claim
          ADD COLUMN assertion  text   NOT NULL DEFAULT '',
          ADD COLUMN qualifiers text[] NOT NULL DEFAULT '{}';
        """
    )
    # Il registro raggruppa per proposizione dentro un processo: e' la query
    # che decide chi e' corroborato e chi no.
    op.execute(
        "CREATE INDEX kg_claim_process_assertion ON kg_claim (process_id, assertion) "
        "WHERE process_id IS NOT NULL;"
    )


def downgrade() -> None:
    """Drop the proposition key and the qualifiers."""
    op.execute("DROP INDEX IF EXISTS kg_claim_process_assertion;")
    op.execute(
        """
        ALTER TABLE kg_claim
          DROP COLUMN IF EXISTS assertion,
          DROP COLUMN IF EXISTS qualifiers;
        """
    )
