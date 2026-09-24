"""Add editable About page content

Revision ID: c74a91d2f6e8
Revises: 99316b4ace03
Create Date: 2026-09-24

"""

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "c74a91d2f6e8"
down_revision = "99316b4ace03"
branch_labels = None
depends_on = None


def upgrade():
    about_pages = op.create_table(
        "about_pages",
        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
        ),
        sa.Column(
            "teacher_name",
            sa.String(length=200),
            nullable=False,
        ),
        sa.Column(
            "role_title",
            sa.String(length=200),
            nullable=False,
        ),
        sa.Column(
            "hero_title",
            sa.String(length=300),
            nullable=False,
        ),
        sa.Column(
            "about_text",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "vision_text",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "mission_text",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "email",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "years_experience",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "questions_count",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "initiatives_count",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "programs_count",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
        ),
    )

    op.bulk_insert(
        about_pages,
        [
            {
                "id": 1,
                "teacher_name": (
                    "إيمان محمد موسى ريان"
                ),
                "role_title": (
                    "معلمة دراسات تاريخية"
                ),
                "hero_title": (
                    "نصنع من التاريخ تجربة "
                    "تعلّم حيّة وقريبة"
                ),
                "about_text": (
                    "معلمة دراسات تاريخية بخبرة "
                    "تتجاوز 16 عامًا في التعليم، "
                    "تجمع بين المعرفة الأكاديمية "
                    "واستراتيجيات التعلم النشط "
                    "والتقنيات الحديثة لتقديم التاريخ "
                    "بطريقة واضحة وتفاعلية."
                ),
                "vision_text": (
                    "تقديم تجربة تعليمية رقمية تجعل "
                    "التاريخ أكثر وضوحًا ومتعة، وتمنح "
                    "الطالبة مساحة للفهم والتحليل "
                    "والتعلّم بثقة."
                ),
                "mission_text": (
                    "تطوير محتوى موثوق وأنشطة تفاعلية "
                    "وتغذية راجعة عملية، مع توظيف "
                    "التكنولوجيا والذكاء الاصطناعي "
                    "لخدمة تعلم الطالبات."
                ),
                "email": (
                    "miss.emmy2020@gmail.com"
                ),
                "years_experience": 16,
                "questions_count": 500,
                "initiatives_count": 10,
                "programs_count": 8,
                "updated_at": datetime.now(
                    timezone.utc
                ).replace(tzinfo=None),
            }
        ],
    )


def downgrade():
    op.drop_table("about_pages")
