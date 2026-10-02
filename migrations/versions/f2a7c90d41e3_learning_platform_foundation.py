"""Learning platform foundation.

Revision ID: f2a7c90d41e3
Revises: d4c8f61a2e90
"""
from alembic import op
import sqlalchemy as sa

revision = "f2a7c90d41e3"
down_revision = "d4c8f61a2e90"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("curricula") as batch:
        batch.drop_constraint("uq_curriculum_version", type_="unique")
        batch.add_column(sa.Column("created_by_id", sa.Integer(), nullable=True))
        batch.create_index("ix_curricula_created_by_id", ["created_by_id"])
        batch.create_foreign_key("fk_curricula_creator", "users", ["created_by_id"], ["id"], ondelete="SET NULL")
        batch.create_unique_constraint("uq_curriculum_version", ["created_by_id", "subject", "grade", "semester", "academic_year", "version"])

    with op.batch_alter_table("worksheets") as batch:
        batch.add_column(sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("archived_at", sa.DateTime(), nullable=True))
        batch.create_index("ix_worksheets_is_archived", ["is_archived"])

    op.create_table("platform_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("platform_name", sa.String(150), nullable=False),
        sa.Column("tagline", sa.String(250), nullable=False),
        sa.Column("whatsapp_url", sa.String(500)), sa.Column("support_email", sa.String(255)),
        sa.Column("updated_at", sa.DateTime(), nullable=False))
    op.create_table("classrooms",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("teacher_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False), sa.Column("grade", sa.String(50), nullable=False),
        sa.Column("academic_year", sa.String(30), nullable=False), sa.Column("whatsapp_url", sa.String(500)),
        sa.Column("is_active", sa.Boolean(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("teacher_id", "name", "academic_year", name="uq_teacher_classroom_year"))
    op.create_index("ix_classrooms_teacher_id", "classrooms", ["teacher_id"])
    op.create_table("class_enrollments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("classroom_id", sa.Integer(), sa.ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("joined_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("classroom_id", "student_id", name="uq_classroom_student"))
    op.create_index("ix_class_enrollments_classroom_id", "class_enrollments", ["classroom_id"])
    op.create_index("ix_class_enrollments_student_id", "class_enrollments", ["student_id"])
    op.create_table("student_invitations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("teacher_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("classroom_id", sa.Integer(), sa.ForeignKey("classrooms.id", ondelete="SET NULL")),
        sa.Column("email", sa.String(255), nullable=False), sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False), sa.Column("accepted_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_index("ix_student_invitations_teacher_id", "student_invitations", ["teacher_id"])
    op.create_index("ix_student_invitations_classroom_id", "student_invitations", ["classroom_id"])
    op.create_index("ix_student_invitations_email", "student_invitations", ["email"])
    op.create_table("learning_resources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lesson_id", sa.Integer(), sa.ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("title", sa.String(250), nullable=False), sa.Column("resource_type", sa.String(40), nullable=False),
        sa.Column("creation_method", sa.String(30), nullable=False), sa.Column("description", sa.Text()),
        sa.Column("original_filename", sa.String(255)), sa.Column("stored_path", sa.String(500)),
        sa.Column("mime_type", sa.String(150)), sa.Column("allow_download", sa.Boolean(), nullable=False),
        sa.Column("publication_status", sa.String(30), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_index("ix_learning_resources_lesson_id", "learning_resources", ["lesson_id"])
    op.create_index("ix_learning_resources_created_by_id", "learning_resources", ["created_by_id"])
    op.create_index("ix_learning_resources_resource_type", "learning_resources", ["resource_type"])
    op.create_index("ix_learning_resources_publication_status", "learning_resources", ["publication_status"])
    op.create_table("concept_maps",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lesson_id", sa.Integer(), sa.ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("title", sa.String(250), nullable=False), sa.Column("map_type", sa.String(40), nullable=False),
        sa.Column("creation_method", sa.String(30), nullable=False), sa.Column("publication_status", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_index("ix_concept_maps_lesson_id", "concept_maps", ["lesson_id"])
    op.create_index("ix_concept_maps_created_by_id", "concept_maps", ["created_by_id"])
    op.create_table("concept_map_nodes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("concept_map_id", sa.Integer(), sa.ForeignKey("concept_maps.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.String(250), nullable=False), sa.Column("description", sa.Text()),
        sa.Column("position_x", sa.Float(), nullable=False), sa.Column("position_y", sa.Float(), nullable=False))
    op.create_index("ix_concept_map_nodes_concept_map_id", "concept_map_nodes", ["concept_map_id"])
    op.create_table("concept_map_edges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("concept_map_id", sa.Integer(), sa.ForeignKey("concept_maps.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_node_id", sa.Integer(), sa.ForeignKey("concept_map_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_node_id", sa.Integer(), sa.ForeignKey("concept_map_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.String(150)))
    op.create_index("ix_concept_map_edges_concept_map_id", "concept_map_edges", ["concept_map_id"])
    op.create_table("historical_characters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lesson_id", sa.Integer(), sa.ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("name", sa.String(200), nullable=False), sa.Column("period", sa.String(150)),
        sa.Column("summary", sa.Text(), nullable=False), sa.Column("key_events", sa.Text()), sa.Column("source_notes", sa.Text()),
        sa.Column("publication_status", sa.String(30), nullable=False), sa.Column("is_ai_generated", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("lesson_id", "name", name="uq_lesson_character"))
    op.create_index("ix_historical_characters_lesson_id", "historical_characters", ["lesson_id"])
    op.create_index("ix_historical_characters_created_by_id", "historical_characters", ["created_by_id"])


def downgrade():
    for table in ["historical_characters", "concept_map_edges", "concept_map_nodes", "concept_maps", "learning_resources", "student_invitations", "class_enrollments", "classrooms", "platform_settings"]:
        op.drop_table(table)
    with op.batch_alter_table("worksheets") as batch:
        batch.drop_index("ix_worksheets_is_archived")
        batch.drop_column("archived_at"); batch.drop_column("is_archived")
    with op.batch_alter_table("curricula") as batch:
        batch.drop_constraint("uq_curriculum_version", type_="unique")
        batch.drop_constraint("fk_curricula_creator", type_="foreignkey")
        batch.drop_index("ix_curricula_created_by_id")
        batch.drop_column("created_by_id")
        batch.create_unique_constraint("uq_curriculum_version", ["grade", "semester", "academic_year", "version"])
