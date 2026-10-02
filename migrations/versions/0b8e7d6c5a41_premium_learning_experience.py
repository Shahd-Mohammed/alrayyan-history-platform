"""Premium learning experience and safe content lifecycle.

Revision ID: 0b8e7d6c5a41
Revises: f2a7c90d41e3
"""
from alembic import op
import sqlalchemy as sa


revision = "0b8e7d6c5a41"
down_revision = "f2a7c90d41e3"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("curricula") as batch:
        batch.add_column(sa.Column("processing_status", sa.String(30), nullable=False, server_default="ready"))
        batch.add_column(sa.Column("processing_error", sa.Text(), nullable=True))
        batch.add_column(sa.Column("activated_at", sa.DateTime(), nullable=True))
        batch.create_index("ix_curricula_processing_status", ["processing_status"])

    with op.batch_alter_table("concept_maps") as batch:
        batch.add_column(sa.Column("original_filename", sa.String(255), nullable=True))
        batch.add_column(sa.Column("stored_path", sa.String(500), nullable=True))
        batch.add_column(sa.Column("mime_type", sa.String(150), nullable=True))

    with op.batch_alter_table("historical_characters") as batch:
        batch.add_column(sa.Column("clues", sa.Text(), nullable=True))

    # Older AI drafts stored the game clues inside source_notes. Separate them
    # without inventing content, while keeping the source paragraph intact.
    connection = op.get_bind()
    old_rows = connection.execute(sa.text(
        "SELECT id, source_notes FROM historical_characters "
        "WHERE source_notes IS NOT NULL AND clues IS NULL"
    )).mappings()
    for row in old_rows:
        notes = row["source_notes"] or ""
        marker = "تلميحات من أنا؟"
        if marker not in notes:
            continue
        source_part, clue_part = notes.split(marker, 1)
        clues = "\n".join(
            line.strip().lstrip("-•✦ ")
            for line in clue_part.splitlines()
            if line.strip().lstrip("-•✦ ")
        )[:3000]
        connection.execute(
            sa.text("UPDATE historical_characters SET clues=:clues, source_notes=:source WHERE id=:id"),
            {"clues": clues or None, "source": source_part.strip() or None, "id": row["id"]},
        )

    op.create_table(
        "character_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("character_id", sa.Integer(), sa.ForeignKey("historical_characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("answer_text", sa.String(250), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("hints_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("xp_awarded", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempted_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("character_id", "student_id", name="uq_character_student_attempt"),
    )
    op.create_index("ix_character_attempts_character_id", "character_attempts", ["character_id"])
    op.create_index("ix_character_attempts_student_id", "character_attempts", ["student_id"])

    op.create_table(
        "honor_board_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("teacher_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("note", sa.String(300)),
        sa.Column("period_label", sa.String(100)),
        sa.Column("is_manual", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_honor_board_entries_teacher_id", "honor_board_entries", ["teacher_id"])
    op.create_index("ix_honor_board_entries_student_id", "honor_board_entries", ["student_id"])


def downgrade():
    op.drop_table("honor_board_entries")
    op.drop_table("character_attempts")
    with op.batch_alter_table("historical_characters") as batch:
        batch.drop_column("clues")
    with op.batch_alter_table("concept_maps") as batch:
        batch.drop_column("mime_type")
        batch.drop_column("stored_path")
        batch.drop_column("original_filename")
    with op.batch_alter_table("curricula") as batch:
        batch.drop_index("ix_curricula_processing_status")
        batch.drop_column("activated_at")
        batch.drop_column("processing_error")
        batch.drop_column("processing_status")
