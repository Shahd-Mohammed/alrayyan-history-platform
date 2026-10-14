"""Preserve existing concept mastery records during the tutor scoring transition.

The earlier reset targeted a singular table name that does not match the
ConceptMastery model (concept_masteries). Resetting stored scores would also
silently change existing student progress. Keep this revision in the Alembic
chain without rewriting student data; any future recalculation must be an
explicit, reviewed operation.
"""

revision = "c3e8a1b7d902"
down_revision = "0b8e7d6c5a41"
branch_labels = None
depends_on = None


def upgrade():
    # Intentionally preserve existing mastery scores and student data.
    pass


def downgrade():
    # No database changes were made by upgrade().
    pass
