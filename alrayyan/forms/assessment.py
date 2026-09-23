from flask_wtf import FlaskForm

from wtforms import (
    BooleanField,
    FloatField,
    IntegerField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)

from wtforms.validators import (
    DataRequired,
    Length,
    NumberRange,
    Optional,
)


class QuestionForm(FlaskForm):
    """
    Form used by the teacher to create
    an interactive worksheet question.
    """

    question_text = TextAreaField(
        "نص السؤال",
        validators=[
            DataRequired(
                message="يرجى كتابة نص السؤال."
            ),
            Length(
                max=3000,
                message="نص السؤال طويل جدًا.",
            ),
        ],
    )

    question_type = SelectField(
        "نوع السؤال",
        choices=[
            (
                "multiple_choice",
                "اختيار من متعدد",
            ),
            (
                "true_false",
                "صح أو خطأ",
            ),
            (
                "short_answer",
                "إجابة قصيرة",
            ),
            (
                "essay",
                "سؤال مقالي",
            ),
        ],
        validators=[
            DataRequired()
        ],
    )

    choices_text = TextAreaField(
        "الخيارات",
        validators=[
            Optional(),
            Length(max=3000),
        ],
        description=(
            "اكتبي كل خيار في سطر مستقل."
        ),
    )

    correct_answer_text = StringField(
        "الإجابة الصحيحة",
        validators=[
            Optional(),
            Length(max=1000),
        ],
    )

    explanation = TextAreaField(
        "تفسير الإجابة",
        validators=[
            Optional(),
            Length(max=3000),
        ],
    )

    points = FloatField(
        "درجة السؤال",
        validators=[
            DataRequired(
                message="يرجى تحديد الدرجة."
            ),
            NumberRange(
                min=0.5,
                max=100,
                message=(
                    "يجب أن تكون الدرجة "
                    "بين 0.5 و100."
                ),
            ),
        ],
        default=1,
    )

    submit = SubmitField(
        "حفظ السؤال"
    )


class WorksheetSettingsForm(FlaskForm):
    """
    Form used to configure how students
    solve the interactive worksheet.
    """

    time_limit_minutes = IntegerField(
        "مدة الحل بالدقائق",
        validators=[
            Optional(),
            NumberRange(
                min=1,
                max=300,
                message=(
                    "مدة الحل يجب أن تكون "
                    "بين دقيقة و300 دقيقة."
                ),
            ),
        ],
    )

    passing_score = FloatField(
        "نسبة النجاح",
        validators=[
            DataRequired(
                message="يرجى تحديد نسبة النجاح."
            ),
            NumberRange(
                min=0,
                max=100,
                message=(
                    "نسبة النجاح يجب أن تكون "
                    "بين صفر و100."
                ),
            ),
        ],
        default=50,
    )

    max_attempts = IntegerField(
    "الحد الأقصى للمحاولات",
    validators=[
        DataRequired(
            message=(
                "يرجى تحديد عدد المحاولات."
            )
        ),
        NumberRange(
            min=1,
            max=20,
            message=(
                "عدد المحاولات يجب أن يكون "
                "بين محاولة واحدة و20 محاولة."
            ),
        ),
    ],
    default=3,
    )

    show_answers_after_submit = BooleanField(
        "إظهار الإجابات بعد التسليم",
        default=True,
    )

    submit = SubmitField(
        "حفظ إعدادات الحل"
    )