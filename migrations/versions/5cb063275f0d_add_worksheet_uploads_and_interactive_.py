"""Add worksheet uploads and interactive activities

Revision ID: 5cb063275f0d
Revises: 4cc952e4e6af
Create Date: 2026-09-21 10:16:40.884368
"""

from alembic import op
import sqlalchemy as sa


revision = "5cb063275f0d"
down_revision = "4cc952e4e6af"
branch_labels = None
depends_on = None


def get_column_names(inspector, table_name):
    return {
        column["name"]
        for column in inspector.get_columns(table_name)
    }


def get_index_names(inspector, table_name):
    return {
        index["name"]
        for index in inspector.get_indexes(table_name)
    }


def upgrade():
    connection = op.get_bind()
    inspector = sa.inspect(connection)

    table_names = set(
        inspector.get_table_names()
    )

    if "worksheet_attachments" not in table_names:
        op.create_table(
            "worksheet_attachments",
            sa.Column(
                "id",
                sa.Integer(),
                nullable=False,
            ),
            sa.Column(
                "worksheet_id",
                sa.Integer(),
                nullable=False,
            ),
            sa.Column(
                "attachment_type",
                sa.String(length=30),
                nullable=False,
                server_default="worksheet",
            ),
            sa.Column(
                "original_filename",
                sa.String(length=255),
                nullable=False,
            ),
            sa.Column(
                "stored_filename",
                sa.String(length=255),
                nullable=False,
            ),
            sa.Column(
                "storage_path",
                sa.String(length=500),
                nullable=False,
            ),
            sa.Column(
                "file_extension",
                sa.String(length=20),
                nullable=False,
            ),
            sa.Column(
                "mime_type",
                sa.String(length=150),
                nullable=True,
            ),
            sa.Column(
                "file_size",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["worksheet_id"],
                ["worksheets.id"],
                name=(
                    "fk_worksheet_attachments_"
                    "worksheet_id_worksheets"
                ),
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "stored_filename",
                name=(
                    "uq_worksheet_attachments_"
                    "stored_filename"
                ),
            ),
        )

        op.create_index(
            "ix_worksheet_attachments_worksheet_id",
            "worksheet_attachments",
            ["worksheet_id"],
            unique=False,
        )

    else:
        attachment_indexes = get_index_names(
            inspector,
            "worksheet_attachments",
        )

        if (
            "ix_worksheet_attachments_worksheet_id"
            not in attachment_indexes
        ):
            op.create_index(
                "ix_worksheet_attachments_worksheet_id",
                "worksheet_attachments",
                ["worksheet_id"],
                unique=False,
            )

    question_columns = get_column_names(
        inspector,
        "questions",
    )

    if (
        "interaction_config" not in question_columns
        or "requires_manual_grading"
        not in question_columns
    ):
        with op.batch_alter_table(
            "questions",
            schema=None,
        ) as batch_op:
            if "interaction_config" not in question_columns:
                batch_op.add_column(
                    sa.Column(
                        "interaction_config",
                        sa.Text(),
                        nullable=True,
                    )
                )

            if (
                "requires_manual_grading"
                not in question_columns
            ):
                batch_op.add_column(
                    sa.Column(
                        "requires_manual_grading",
                        sa.Boolean(),
                        nullable=False,
                        server_default=sa.false(),
                    )
                )

    answer_columns = get_column_names(
        inspector,
        "student_answers",
    )

    missing_answer_columns = {
        "answer_data",
        "teacher_feedback",
        "graded_at",
    } - answer_columns

    if missing_answer_columns:
        with op.batch_alter_table(
            "student_answers",
            schema=None,
        ) as batch_op:
            if "answer_data" in missing_answer_columns:
                batch_op.add_column(
                    sa.Column(
                        "answer_data",
                        sa.Text(),
                        nullable=True,
                    )
                )

            if "teacher_feedback" in missing_answer_columns:
                batch_op.add_column(
                    sa.Column(
                        "teacher_feedback",
                        sa.Text(),
                        nullable=True,
                    )
                )

            if "graded_at" in missing_answer_columns:
                batch_op.add_column(
                    sa.Column(
                        "graded_at",
                        sa.DateTime(),
                        nullable=True,
                    )
                )

    worksheet_columns = get_column_names(
        inspector,
        "worksheets",
    )

    worksheet_indexes = get_index_names(
        inspector,
        "worksheets",
    )

    worksheet_foreign_keys = (
        inspector.get_foreign_keys("worksheets")
    )

    creator_foreign_key_exists = any(
        foreign_key.get("constrained_columns")
        == ["created_by_id"]
        for foreign_key in worksheet_foreign_keys
    )

    required_worksheet_columns = {
        "created_by_id",
        "creation_method",
        "difficulty_level",
        "publication_status",
        "allow_download",
        "is_ai_generated",
    }

    missing_worksheet_columns = (
        required_worksheet_columns
        - worksheet_columns
    )

    indexes_are_missing = any(
        index_name not in worksheet_indexes
        for index_name in {
            "ix_worksheets_created_by_id",
            "ix_worksheets_creation_method",
            "ix_worksheets_publication_status",
        }
    )

    if (
        missing_worksheet_columns
        or indexes_are_missing
        or not creator_foreign_key_exists
    ):
        with op.batch_alter_table(
            "worksheets",
            schema=None,
        ) as batch_op:
            if "created_by_id" in missing_worksheet_columns:
                batch_op.add_column(
                    sa.Column(
                        "created_by_id",
                        sa.Integer(),
                        nullable=True,
                    )
                )

            if "creation_method" in missing_worksheet_columns:
                batch_op.add_column(
                    sa.Column(
                        "creation_method",
                        sa.String(length=30),
                        nullable=False,
                        server_default="manual",
                    )
                )

            if "difficulty_level" in missing_worksheet_columns:
                batch_op.add_column(
                    sa.Column(
                        "difficulty_level",
                        sa.String(length=30),
                        nullable=False,
                        server_default="medium",
                    )
                )

            if (
                "publication_status"
                in missing_worksheet_columns
            ):
                batch_op.add_column(
                    sa.Column(
                        "publication_status",
                        sa.String(length=30),
                        nullable=False,
                        server_default="draft",
                    )
                )

            if "allow_download" in missing_worksheet_columns:
                batch_op.add_column(
                    sa.Column(
                        "allow_download",
                        sa.Boolean(),
                        nullable=False,
                        server_default=sa.true(),
                    )
                )

            if (
                "is_ai_generated"
                in missing_worksheet_columns
            ):
                batch_op.add_column(
                    sa.Column(
                        "is_ai_generated",
                        sa.Boolean(),
                        nullable=False,
                        server_default=sa.false(),
                    )
                )

            if (
                "ix_worksheets_created_by_id"
                not in worksheet_indexes
            ):
                batch_op.create_index(
                    "ix_worksheets_created_by_id",
                    ["created_by_id"],
                    unique=False,
                )

            if (
                "ix_worksheets_creation_method"
                not in worksheet_indexes
            ):
                batch_op.create_index(
                    "ix_worksheets_creation_method",
                    ["creation_method"],
                    unique=False,
                )

            if (
                "ix_worksheets_publication_status"
                not in worksheet_indexes
            ):
                batch_op.create_index(
                    "ix_worksheets_publication_status",
                    ["publication_status"],
                    unique=False,
                )

            if not creator_foreign_key_exists:
                batch_op.create_foreign_key(
                    "fk_worksheets_created_by_id_users",
                    "users",
                    ["created_by_id"],
                    ["id"],
                    ondelete="SET NULL",
                )


def downgrade():
    with op.batch_alter_table(
        "worksheets",
        schema=None,
    ) as batch_op:
        batch_op.drop_constraint(
            "fk_worksheets_created_by_id_users",
            type_="foreignkey",
        )
        batch_op.drop_index(
            "ix_worksheets_publication_status"
        )
        batch_op.drop_index(
            "ix_worksheets_creation_method"
        )
        batch_op.drop_index(
            "ix_worksheets_created_by_id"
        )
        batch_op.drop_column("is_ai_generated")
        batch_op.drop_column("allow_download")
        batch_op.drop_column("publication_status")
        batch_op.drop_column("difficulty_level")
        batch_op.drop_column("creation_method")
        batch_op.drop_column("created_by_id")

    with op.batch_alter_table(
        "student_answers",
        schema=None,
    ) as batch_op:
        batch_op.drop_column("graded_at")
        batch_op.drop_column("teacher_feedback")
        batch_op.drop_column("answer_data")

    with op.batch_alter_table(
        "questions",
        schema=None,
    ) as batch_op:
        batch_op.drop_column(
            "requires_manual_grading"
        )
        batch_op.drop_column(
            "interaction_config"
        )

    op.drop_index(
        "ix_worksheet_attachments_worksheet_id",
        table_name="worksheet_attachments",
    )

    op.drop_table("worksheet_attachments")