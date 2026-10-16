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
    op.alter_column(
        "tutor_messages",
        "prompt_version",
        existing_type=sa.String(length=30),
        type_=sa.String(length=100),
        existing_nullable=True,
    )


def downgrade():
    # Refuse to narrow the column if longer values exist; never truncate metadata.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM tutor_messages
                WHERE length(prompt_version) > 30
            ) THEN
                RAISE EXCEPTION
                    'Cannot downgrade prompt_version: values longer than 30 characters exist.';
            END IF;
        END $$;
        """
    )
    op.alter_column(
        "tutor_messages",
        "prompt_version",
        existing_type=sa.String(length=100),
        type_=sa.String(length=30),
        existing_nullable=True,
    )
