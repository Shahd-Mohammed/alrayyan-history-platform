"""Allow version identifiers longer than 30 characters.

Revision ID: a7f16c2e9b40
Revises: c3e8a1b7d902
"""
from alembic import op
import sqlalchemy as sa


revision = "a7f16c2e9b40"
down_revision = "c3e8a1b7d902"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("tutor_messages") as batch_op:
        batch_op.alter_column(
            "prompt_version",
            existing_type=sa.String(length=30),
            type_=sa.String(length=100),
            existing_nullable=True,
        )


def downgrade():
    # Refuse to narrow the column if longer values exist; never truncate metadata.
    connection = op.get_bind()
    has_long_values = connection.execute(
        sa.text(
            "SELECT 1 FROM tutor_messages "
            "WHERE length(prompt_version) > 30 LIMIT 1"
        )
    ).first()
    if has_long_values:
        raise RuntimeError(
            "Cannot downgrade prompt_version: values longer than 30 characters exist."
        )

    with op.batch_alter_table("tutor_messages") as batch_op:
        batch_op.alter_column(
            "prompt_version",
            existing_type=sa.String(length=100),
            type_=sa.String(length=30),
            existing_nullable=True,
        )
