"""Reunite the concurrently published 0031 merge revisions.

Revision ID: 0032_merge_layout_heads
Revises: 0031_merge_0030_heads, 0031_merge_review_simulation

PRs #96 and #97 each repaired the parallel 0030 heads, then merged concurrently.
Keep both published histories and restore one upgrade head without schema DDL.
"""

revision = "0032_merge_layout_heads"
down_revision = ("0031_merge_0030_heads", "0031_merge_review_simulation")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
