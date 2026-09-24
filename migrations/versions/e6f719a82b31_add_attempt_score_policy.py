"""Add worksheet attempt score policy

Revision ID: e6f719a82b31
Revises: c74a91d2f6e8
Create Date: 2026-09-24

"""

from alembic import op
import sqlalchemy as sa


revision = "e6f719a82b31"
down_revision = "c74a91d2f6e8"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table(
        "worksheets",
        schema=None,
    ) as batch_op:
        batch_op.alter_column(
            "lesson_id",
            existing_type=sa.Integer(),
            nullable=True,
        )
        batch_op.add_column(
            sa.Column(
                "attempt_score_policy",
                sa.String(length=20),
                server_default="highest",
                nullable=False,
            )
        )


def downgrade():
    with op.batch_alter_table(
        "worksheets",
        schema=None,
    ) as batch_op:
        batch_op.alter_column(
            "lesson_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch_op.drop_column(
            "attempt_score_policy"
        )
