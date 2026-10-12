"""Il link privato del cruscotto del responsabile del processo."""
from alembic import op
import sqlalchemy as sa

revision = "0036_owner_dashboard_links"
down_revision = "0035_simulation_scenarios"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0001 crea le tabelle dai metadati ORM su un database nuovo, questa compresa.
    if sa.inspect(op.get_bind()).has_table("workspace_owner_dashboard_links"):
        return
    op.create_table(
        "workspace_owner_dashboard_links",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("process_id", sa.String(), sa.ForeignKey("workspace_processes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("expires_at", sa.String(), nullable=False),
        sa.Column("revoked_at", sa.String(), nullable=True),
        sa.Column("last_viewed_at", sa.String(), nullable=True),
        sa.Column("view_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_owner_dashboard_links_process_tenant", "workspace_owner_dashboard_links", ["process_id", "tenant_id"])


def downgrade() -> None:
    op.drop_table("workspace_owner_dashboard_links")
