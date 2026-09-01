"""RLS: policy di isolamento tenant su tutte le tabelle con dati

Revision ID: 0005_rls_policies
Revises: 0004_outbox_log
Create Date: 2026-09-01

Copre: INV-6 (RLS realmente enforceata), INV-9 (unico punto di scope in lettura).

- consultant: ENABLE (non FORCE) -> l'owner delir_migrator puo' seedare i
  consulenti; delir_app vede solo se stesso.
- client / project / process / kg_source / kg_chunk / *_memory: ENABLE + FORCE
  -> anche l'owner obbedisce. Policy unica FOR ALL con USING = WITH CHECK.

Due forme di predicato:
- tabelle con client_id nullable (memoria, source, chunk):
    consultant_id = app_consultant_id()
    AND (client_id IS NULL OR client_id = app_client_id())
  -> le righe consultant-scoped (client_id NULL) sono sempre visibili;
     le client-scoped solo nel contesto di quel cliente.
- tabelle senza righe consultant-scoped (client, project, process):
    consultant_id = app_consultant_id()
    AND (app_client_id() IS NULL OR <ref_cliente> = app_client_id())
  -> in contesto solo-consultant vedi tutto il tuo; in contesto cliente
     solo quel cliente.

graph_outbox / mem0_projection_log: niente RLS (sono code, payload gia' scoped,
delir_app ha solo INSERT).
"""

from __future__ import annotations

from alembic import op

revision = "0005_rls_policies"
down_revision = "0004_outbox_log"
branch_labels = None
depends_on = None

# tabelle con client_id nullable + righe consultant-scoped
_NULLABLE_CLIENT = [
    "kg_source",
    "kg_chunk",
    "semantic_memory",
    "episodic_memory",
    "procedural_memory",
]

# (tabella, espressione che identifica il cliente della riga)
_STRICT_CLIENT = [
    ("client", "id"),
    ("project", "client_id"),
    ("process", "client_id"),
]


def upgrade() -> None:
    # --- consultant: solo se stesso ------------------------------------
    op.execute("ALTER TABLE consultant ENABLE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY consultant_self ON consultant
          USING (id = app_consultant_id())
          WITH CHECK (id = app_consultant_id());
        """
    )

    # --- client / project / process ----------------------------------
    for table, client_ref in _STRICT_CLIENT:
        pred = (
            f"consultant_id = app_consultant_id() "
            f"AND (app_client_id() IS NULL OR {client_ref} = app_client_id())"
        )
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        op.execute(
            f"CREATE POLICY {table}_tenant ON {table} "
            f"USING ({pred}) WITH CHECK ({pred});"
        )

    # --- memoria / source / chunk -----------------------------------
    for table in _NULLABLE_CLIENT:
        pred = (
            "consultant_id = app_consultant_id() "
            "AND (client_id IS NULL OR client_id = app_client_id())"
        )
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        op.execute(
            f"CREATE POLICY {table}_tenant ON {table} "
            f"USING ({pred}) WITH CHECK ({pred});"
        )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS consultant_self ON consultant;")
    op.execute("ALTER TABLE consultant DISABLE ROW LEVEL SECURITY;")
    for table, _ in _STRICT_CLIENT:
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant ON {table};")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")
    for table in _NULLABLE_CLIENT:
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant ON {table};")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")
