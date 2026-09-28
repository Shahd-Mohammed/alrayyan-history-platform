"""Verify learning-plan reviews with challenge sessions.

Revision ID: d4c8f61a2e90
Revises: b7e4d21c8a90
"""

from alembic import op
import sqlalchemy as sa


revision = "d4c8f61a2e90"
down_revision = "b7e4d21c8a90"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("learning_plan_items") as batch_op:
        batch_op.add_column(sa.Column("verification_score", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("verified_at", sa.DateTime(), nullable=True))

    with op.batch_alter_table("challenge_sessions") as batch_op:
        batch_op.add_column(sa.Column("learning_plan_item_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_challenge_session_learning_plan_item",
            "learning_plan_items",
            ["learning_plan_item_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_challenge_sessions_learning_plan_item_id",
            ["learning_plan_item_id"],
        )


def downgrade():
    with op.batch_alter_table("challenge_sessions") as batch_op:
        batch_op.drop_index("ix_challenge_sessions_learning_plan_item_id")
        batch_op.drop_constraint(
            "fk_challenge_session_learning_plan_item",
            type_="foreignkey",
        )
        batch_op.drop_column("learning_plan_item_id")

    with op.batch_alter_table("learning_plan_items") as batch_op:
        batch_op.drop_column("verified_at")
        batch_op.drop_column("verification_score")
