"""Il registro dei consumi: un evento per ogni chiamata al modello.

Revision ID: 0014_llm_usage_ledger
Revises: 0013_conformance_lease
Create Date: 2026-09-20

Il 18/09 il credito OpenAI si e' esaurito e non c'era modo di sapere dove fosse
andato: dieci moduli chiamavano il modello, ognuno con il suo client, e nessun
punto di passaggio unico. LangSmith aveva esaurito la quota il 6/9, e la chiave
del progetto non ha `api.usage.read`. La domanda «dove sono andati i soldi ieri»
non aveva nessun posto in cui essere fatta.

Questa tabella e' quel posto. Le dimensioni sono quelle con cui si legge la
spesa: tenant, operazione, compito, modello.

Due cose che sembrano difetti e sono decisioni:

- si scrive una riga **anche** per i guasti e per i colpi di cache. Un timeout si
  paga, e una chiamata evitata e' il risultato migliore possibile: senza una riga
  non potremmo dimostrare di averla evitata;
- `cost_estimate` e' NULLABLE. NULL significa "questo modello non ha un prezzo
  configurato", non "questa chiamata e' stata gratis". I token restano contati, e
  il costo si ricalcola quando il listino c'e'. Un prezzo inventato per non
  lasciare NULL sarebbe plausibile e falso, e ci si farebbero i budget sopra.

Nessun backfill: prima di oggi il dato non esiste. La tabella parte vuota, ed e'
corretto che le serie storiche cominchino da qui.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014_llm_usage_ledger"
down_revision = "0013_conformance_lease"
branch_labels = None
depends_on = None

_TABLE = "workspace_llm_usage"


def _tables(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    if _TABLE in _tables(bind):
        return

    op.create_table(
        _TABLE,
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False, server_default="local"),
        sa.Column("operation_kind", sa.String(), nullable=False),
        sa.Column("operation_id", sa.String(), nullable=False),
        sa.Column("parent_operation_id", sa.String()),
        sa.Column("project_id", sa.String()),
        sa.Column("process_id", sa.String()),
        sa.Column("task", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("prompt_version", sa.String()),
        sa.Column("reasoning_effort", sa.String()),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reasoning_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cached_input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("error_kind", sa.String()),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("cost_estimate", sa.String()),
        sa.Column("created_at", sa.String(), nullable=False),
    )

    # Indici singoli sulle dimensioni con cui si filtra.
    for column in ("tenant_id", "operation_kind", "operation_id", "task", "model", "outcome"):
        op.create_index(f"ix_{_TABLE}_{column}", _TABLE, [column])
    for column in ("parent_operation_id", "project_id", "process_id", "created_at"):
        op.create_index(f"ix_{_TABLE}_{column}", _TABLE, [column])

    # La query che si fara' ogni giorno e' «la spesa di questo tenant da ieri»:
    # un indice composto la serve senza scandire la tabella, che in un mese di
    # esercizio avra' molte piu' righe di qualunque altra qui dentro.
    op.create_index(
        f"ix_{_TABLE}_tenant_day",
        _TABLE,
        ["tenant_id", "created_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    if _TABLE not in _tables(bind):
        return
    op.drop_table(_TABLE)
