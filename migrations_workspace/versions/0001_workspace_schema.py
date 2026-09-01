"""schema iniziale del database operativo `workspace`

Revision ID: 0001_workspace_schema
Revises:
Create Date: 2026-09-02

Lo schema operativo (clienti/progetti/processi/BPMN/simulazioni + cronologia
chat + indice memoria episodica) e' definito dai modelli SQLAlchemy nei tre
moduli qui sotto. La revision lo materializza con `metadata.create_all` sulla
connessione Alembic: unica fonte di verita' = i modelli, ma con version
tracking e uno step di deploy controllato (niente DDL all'import).

I checkpoint LangGraph (`checkpoint_*`) NON sono qui: li crea da solo
`PostgresSaver.setup()` (backend/agent_checkpoint.py).
"""

from __future__ import annotations

from alembic import op

revision = "0001_workspace_schema"
down_revision = None
branch_labels = None
depends_on = None


def _metadatas():
    from backend.database import Base as ChatBase
    from backend.memory.episodic.episodic_store import Base as EpisodicBase
    from backend.workspace_storage import WorkspaceBase

    return (WorkspaceBase.metadata, ChatBase.metadata, EpisodicBase.metadata)


def upgrade() -> None:
    bind = op.get_bind()
    for metadata in _metadatas():
        metadata.create_all(bind)


def downgrade() -> None:
    bind = op.get_bind()
    for metadata in reversed(_metadatas()):
        metadata.drop_all(bind)
