"""Store alternative As-Is/To-Be diagrams without replacing the baseline."""
from alembic import op
import sqlalchemy as sa

revision = "0030_review_proposal_diagrams"
down_revision = "0029_impact_review_actions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    table = "workspace_impact_review_actions"
    # 0001 creates current ORM metadata on a fresh database.
    if "proposal_xml" in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}:
        return
    op.add_column(table, sa.Column("proposal_xml", sa.Text(), nullable=True))
    op.drop_constraint("ck_impact_review_kind", table, type_="check")
    op.create_check_constraint("ck_impact_review_kind", table, "kind IN ('candidate', 'as_is_proposal', 'clarification', 'deferred')")


def downgrade() -> None:
    table = "workspace_impact_review_actions"
    op.execute(sa.text("DELETE FROM workspace_impact_review_actions WHERE kind = 'as_is_proposal'"))
    op.drop_constraint("ck_impact_review_kind", table, type_="check")
    op.create_check_constraint("ck_impact_review_kind", table, "kind IN ('candidate', 'clarification', 'deferred')")
    op.drop_column(table, "proposal_xml")
