"""Rebase concept mastery percentages after introducing verified tutor answers.

Existing mastery percentages may include unverified social replies from the older
scoring flow. Reset only the derived percentage; preserve attempts, counters,
points, test results, and conversation history.
"""
from alembic import op
import sqlalchemy as sa


revision = "c3e8a1b7d902"
down_revision = "0b8e7d6c5a41"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        sa.text("UPDATE concept_mastery SET mastery_score = 0")
    )


def downgrade():
    # The old derived scores are intentionally not restored: they may contain
    # unverified increases and are no longer considered trustworthy.
    pass
