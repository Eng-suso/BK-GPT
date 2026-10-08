"""Reunite the independently merged Review and simulation migrations.

Revision ID: 0031_merge_review_simulation
Revises: 0030_review_proposal_diagrams, 0030_simulation_run_logs

Both revisions are already published and may have been applied separately.
Keep their history intact and restore one upgrade head; no schema changes.
"""

revision = "0031_merge_review_simulation"
down_revision = ("0030_review_proposal_diagrams", "0030_simulation_run_logs")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
