"""Add interactive AI tutor memory and learning plans.

Revision ID: b7e4d21c8a90
Revises: a1c9f32b7d10
"""

from alembic import op
import sqlalchemy as sa


revision = "b7e4d21c8a90"
down_revision = "a1c9f32b7d10"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tutor_conversations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("lesson_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("difficulty", sa.String(length=20), nullable=False),
        sa.Column("current_concept", sa.String(length=250), nullable=True),
        sa.Column("tutor_state", sa.String(length=30), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["lesson_id"], ["lessons.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tutor_conversations_student_id", "tutor_conversations", ["student_id"])
    op.create_index("ix_tutor_conversations_lesson_id", "tutor_conversations", ["lesson_id"])
    op.create_index("ix_tutor_conversations_status", "tutor_conversations", ["status"])

    op.create_table(
        "tutor_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=True),
        sa.Column("evaluation", sa.String(length=30), nullable=True),
        sa.Column("concept", sa.String(length=250), nullable=True),
        sa.Column("mastery_delta", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(length=150), nullable=True),
        sa.Column("prompt_version", sa.String(length=30), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["tutor_conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tutor_messages_conversation_id", "tutor_messages", ["conversation_id"])

    op.create_table(
        "concept_masteries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("lesson_id", sa.Integer(), nullable=False),
        sa.Column("concept", sa.String(length=250), nullable=False),
        sa.Column("mastery_score", sa.Integer(), nullable=False),
        sa.Column("correct_count", sa.Integer(), nullable=False),
        sa.Column("partial_count", sa.Integer(), nullable=False),
        sa.Column("incorrect_count", sa.Integer(), nullable=False),
        sa.Column("last_reviewed_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["lesson_id"], ["lessons.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_id", "lesson_id", "concept", name="uq_student_lesson_concept_mastery"),
    )
    op.create_index("ix_concept_masteries_student_id", "concept_masteries", ["student_id"])
    op.create_index("ix_concept_masteries_lesson_id", "concept_masteries", ["lesson_id"])

    op.create_table(
        "learning_plan_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("lesson_id", sa.Integer(), nullable=True),
        sa.Column("item_type", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=250), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["lesson_id"], ["lessons.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_learning_plan_items_student_id", "learning_plan_items", ["student_id"])
    op.create_index("ix_learning_plan_items_lesson_id", "learning_plan_items", ["lesson_id"])
    op.create_index("ix_learning_plan_items_status", "learning_plan_items", ["status"])

    op.create_table(
        "tutor_message_sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("chunk_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["chunk_id"], ["content_chunks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["tutor_messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", "chunk_id", name="uq_tutor_message_chunk"),
    )
    op.create_index("ix_tutor_message_sources_message_id", "tutor_message_sources", ["message_id"])
    op.create_index("ix_tutor_message_sources_chunk_id", "tutor_message_sources", ["chunk_id"])


def downgrade():
    op.drop_index("ix_tutor_message_sources_chunk_id", table_name="tutor_message_sources")
    op.drop_index("ix_tutor_message_sources_message_id", table_name="tutor_message_sources")
    op.drop_table("tutor_message_sources")
    op.drop_index("ix_learning_plan_items_status", table_name="learning_plan_items")
    op.drop_index("ix_learning_plan_items_lesson_id", table_name="learning_plan_items")
    op.drop_index("ix_learning_plan_items_student_id", table_name="learning_plan_items")
    op.drop_table("learning_plan_items")
    op.drop_index("ix_concept_masteries_lesson_id", table_name="concept_masteries")
    op.drop_index("ix_concept_masteries_student_id", table_name="concept_masteries")
    op.drop_table("concept_masteries")
    op.drop_index("ix_tutor_messages_conversation_id", table_name="tutor_messages")
    op.drop_table("tutor_messages")
    op.drop_index("ix_tutor_conversations_status", table_name="tutor_conversations")
    op.drop_index("ix_tutor_conversations_lesson_id", table_name="tutor_conversations")
    op.drop_index("ix_tutor_conversations_student_id", table_name="tutor_conversations")
    op.drop_table("tutor_conversations")
