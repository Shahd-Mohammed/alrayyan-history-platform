from flask_wtf import FlaskForm

from wtforms import (
    IntegerField,
    StringField,
    SubmitField,
    TextAreaField,
)

from wtforms.validators import (
    DataRequired,
    Email,
    Length,
    NumberRange,
)


class AboutPageForm(FlaskForm):
    """Teacher form for editing the public About page."""

    teacher_name = StringField(
        "اسم المعلمة",
        validators=[
            DataRequired(),
            Length(max=200),
        ],
    )

    role_title = StringField(
        "المسمى المهني",
        validators=[
            DataRequired(),
            Length(max=200),
        ],
    )

    hero_title = StringField(
        "العنوان الرئيسي",
        validators=[
            DataRequired(),
            Length(max=300),
        ],
    )

    about_text = TextAreaField(
        "من نحن",
        validators=[
            DataRequired(),
            Length(max=3000),
        ],
    )

    vision_text = TextAreaField(
        "رؤيتنا",
        validators=[
            DataRequired(),
            Length(max=2000),
        ],
    )

    mission_text = TextAreaField(
        "رسالتنا",
        validators=[
            DataRequired(),
            Length(max=2000),
        ],
    )

    email = StringField(
        "بريد التواصل",
        validators=[
            DataRequired(),
            Email(),
            Length(max=255),
        ],
    )

    years_experience = IntegerField(
        "سنوات الخبرة",
        validators=[
            DataRequired(),
            NumberRange(min=0, max=80),
        ],
    )

    questions_count = IntegerField(
        "عدد الأسئلة المعدّة",
        validators=[
            DataRequired(),
            NumberRange(min=0, max=100000),
        ],
    )

    initiatives_count = IntegerField(
        "عدد المبادرات",
        validators=[
            DataRequired(),
            NumberRange(min=0, max=10000),
        ],
    )

    programs_count = IntegerField(
        "عدد البرامج التدريبية",
        validators=[
            DataRequired(),
            NumberRange(min=0, max=10000),
        ],
    )

    submit = SubmitField(
        "حفظ صفحة من نحن"
    )
