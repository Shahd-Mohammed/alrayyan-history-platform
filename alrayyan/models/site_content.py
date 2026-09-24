from datetime import datetime, timezone

from alrayyan.extensions import db


class AboutPage(db.Model):
    """Editable public content for the About page."""

    __tablename__ = "about_pages"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    teacher_name = db.Column(
        db.String(200),
        nullable=False,
        default="إيمان محمد موسى ريان",
    )

    role_title = db.Column(
        db.String(200),
        nullable=False,
        default="معلمة دراسات تاريخية",
    )

    hero_title = db.Column(
        db.String(300),
        nullable=False,
        default=(
            "نصنع من التاريخ تجربة "
            "تعلّم حيّة وقريبة"
        ),
    )

    about_text = db.Column(
        db.Text,
        nullable=False,
    )

    vision_text = db.Column(
        db.Text,
        nullable=False,
    )

    mission_text = db.Column(
        db.Text,
        nullable=False,
    )

    email = db.Column(
        db.String(255),
        nullable=False,
        default="miss.emmy2020@gmail.com",
    )

    years_experience = db.Column(
        db.Integer,
        nullable=False,
        default=16,
    )

    questions_count = db.Column(
        db.Integer,
        nullable=False,
        default=500,
    )

    initiatives_count = db.Column(
        db.Integer,
        nullable=False,
        default=10,
    )

    programs_count = db.Column(
        db.Integer,
        nullable=False,
        default=8,
    )

    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(
            timezone.utc
        ),
        onupdate=lambda: datetime.now(
            timezone.utc
        ),
    )

    @classmethod
    def get_or_create(cls):
        """Return the singleton About page record."""

        content = cls.query.first()

        if content is None:
            content = cls(
                teacher_name=(
                    "إيمان محمد موسى ريان"
                ),
                role_title=(
                    "معلمة دراسات تاريخية"
                ),
                hero_title=(
                    "نصنع من التاريخ تجربة "
                    "تعلّم حيّة وقريبة"
                ),
                about_text=(
                    "معلمة دراسات تاريخية بخبرة "
                    "تتجاوز 16 عامًا في التعليم، "
                    "أجمع بين المعرفة الأكاديمية "
                    "واستراتيجيات التعلم النشط "
                    "والتقنيات الحديثة لتقديم التاريخ "
                    "بطريقة واضحة وتفاعلية."
                ),
                vision_text=(
                    "تقديم تجربة تعليمية رقمية تجعل "
                    "التاريخ أكثر وضوحًا ومتعة، وتمنح "
                    "الطالبة مساحة للفهم والتحليل "
                    "والتعلّم بثقة."
                ),
                mission_text=(
                    "تطوير محتوى موثوق وأنشطة تفاعلية "
                    "وتغذية راجعة عملية، مع توظيف "
                    "التكنولوجيا والذكاء الاصطناعي "
                    "لخدمة تعلم الطالبات."
                ),
                email="miss.emmy2020@gmail.com",
                years_experience=16,
                questions_count=500,
                initiatives_count=10,
                programs_count=8,
            )

            db.session.add(content)
            db.session.commit()

        return content
