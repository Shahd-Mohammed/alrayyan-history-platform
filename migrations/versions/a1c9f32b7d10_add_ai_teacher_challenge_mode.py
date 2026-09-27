"""Add AI Teacher Challenge Mode tables.

Revision ID: a1c9f32b7d10
Revises: e6f719a82b31
"""

from alembic import op
import sqlalchemy as sa


revision = "a1c9f32b7d10"
down_revision = "e6f719a82b31"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "challenge_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("lesson_id", sa.Integer(), nullable=True),
        sa.Column("concept", sa.String(length=250), nullable=True),
        sa.Column("mode", sa.String(length=30), nullable=False),
        sa.Column("initial_difficulty", sa.String(length=20), nullable=False),
        sa.Column("current_difficulty", sa.String(length=20), nullable=False),
        sa.Column("total_rounds", sa.Integer(), nullable=False),
        sa.Column("current_round", sa.Integer(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("xp_earned", sa.Integer(), nullable=False),
        sa.Column("combo", sa.Integer(), nullable=False),
        sa.Column("best_combo", sa.Integer(), nullable=False),
        sa.Column("correct_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["lesson_id"], ["lessons.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_challenge_sessions_lesson_id", "challenge_sessions", ["lesson_id"])
    op.create_index("ix_challenge_sessions_status", "challenge_sessions", ["status"])
    op.create_index("ix_challenge_sessions_student_id", "challenge_sessions", ["student_id"])

    op.create_table(
        "challenge_questions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("question_type", sa.String(length=30), nullable=False),
        sa.Column("options_json", sa.JSON(), nullable=False),
        sa.Column("correct_option_index", sa.Integer(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("hint_one", sa.Text(), nullable=False),
        sa.Column("hint_two", sa.Text(), nullable=False),
        sa.Column("difficulty", sa.String(length=20), nullable=False),
        sa.Column("concept", sa.String(length=250), nullable=True),
        sa.Column("generation_model", sa.String(length=150), nullable=True),
        sa.Column("prompt_version", sa.String(length=30), nullable=False),
        sa.Column("hints_used", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["challenge_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "round_number", name="uq_challenge_session_round"),
    )
    op.create_index("ix_challenge_questions_session_id", "challenge_questions", ["session_id"])

    op.create_table(
        "challenge_answers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("selected_option_index", sa.Integer(), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("evaluation_status", sa.String(length=30), nullable=False),
        sa.Column("feedback", sa.Text(), nullable=False),
        sa.Column("hints_used", sa.Integer(), nullable=False),
        sa.Column("score_awarded", sa.Integer(), nullable=False),
        sa.Column("xp_awarded", sa.Integer(), nullable=False),
        sa.Column("response_time_seconds", sa.Integer(), nullable=True),
        sa.Column("answered_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["question_id"], ["challenge_questions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("question_id"),
    )
    op.create_index("ix_challenge_answers_question_id", "challenge_answers", ["question_id"])
    op.create_index("ix_challenge_answers_student_id", "challenge_answers", ["student_id"])

    op.create_table(
        "challenge_question_sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("chunk_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["chunk_id"], ["content_chunks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_id"], ["challenge_questions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("question_id", "chunk_id", name="uq_challenge_question_chunk"),
    )
    op.create_index("ix_challenge_question_sources_chunk_id", "challenge_question_sources", ["chunk_id"])
    op.create_index("ix_challenge_question_sources_question_id", "challenge_question_sources", ["question_id"])

    op.create_table(
        "xp_transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=100), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "student_id", "reason", "source_type", "source_id",
            name="uq_xp_award_source",
        ),
    )
    op.create_index("ix_xp_transactions_student_id", "xp_transactions", ["student_id"])


def downgrade():
    op.drop_index("ix_xp_transactions_student_id", table_name="xp_transactions")
    op.drop_table("xp_transactions")
    op.drop_index("ix_challenge_question_sources_question_id", table_name="challenge_question_sources")
    op.drop_index("ix_challenge_question_sources_chunk_id", table_name="challenge_question_sources")
    op.drop_table("challenge_question_sources")
    op.drop_index("ix_challenge_answers_student_id", table_name="challenge_answers")
    op.drop_index("ix_challenge_answers_question_id", table_name="challenge_answers")
    op.drop_table("challenge_answers")
    op.drop_index("ix_challenge_questions_session_id", table_name="challenge_questions")
    op.drop_table("challenge_questions")
    op.drop_index("ix_challenge_sessions_student_id", table_name="challenge_sessions")
    op.drop_index("ix_challenge_sessions_status", table_name="challenge_sessions")
    op.drop_index("ix_challenge_sessions_lesson_id", table_name="challenge_sessions")
    op.drop_table("challenge_sessions")
