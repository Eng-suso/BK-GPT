"""Separate Process Review hypotheses from the As-Is plan and diagram."""
from alembic import op
import sqlalchemy as sa

revision = "0029_impact_review_actions"
down_revision = "0028_event_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0001 uses current ORM metadata on a fresh database, including this table.
    if sa.inspect(op.get_bind()).has_table("workspace_impact_review_actions"):
        return
    op.create_table(
        "workspace_impact_review_actions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("process_id", sa.String(), sa.ForeignKey("workspace_processes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_id", sa.String(), nullable=False),
        sa.Column("node_name", sa.String(), nullable=False),
        sa.Column("base_revision", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.CheckConstraint("kind IN ('candidate', 'clarification', 'deferred')", name="ck_impact_review_kind"),
    )
    op.create_index("ix_impact_review_process_tenant", "workspace_impact_review_actions", ["process_id", "tenant_id"])


def downgrade() -> None:
    op.drop_table("workspace_impact_review_actions")
