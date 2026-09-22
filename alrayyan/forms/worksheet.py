from flask_wtf import FlaskForm
from flask_wtf.file import (
    FileAllowed,
    FileField,
    FileRequired,
)
from wtforms import (
    BooleanField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import (
    DataRequired,
    Length,
    Optional,
)


class UploadWorksheetForm(FlaskForm):
    lesson_id = SelectField(
        "الدرس",
        coerce=int,
        validators=[
            DataRequired(
                message="يرجى اختيار الدرس."
            )
        ],
    )

    title = StringField(
        "عنوان ورقة العمل",
        validators=[
            DataRequired(
                message="يرجى كتابة عنوان الورقة."
            ),
            Length(
                max=250,
                message="العنوان طويل جدًا.",
            ),
        ],
    )

    description = TextAreaField(
        "وصف الورقة",
        validators=[
            Length(max=2000)
        ],
    )

    instructions = TextAreaField(
        "تعليمات الطالب",
        validators=[
            Length(max=2000)
        ],
    )

    difficulty_level = SelectField(
        "مستوى الصعوبة",
        choices=[
            ("easy", "سهل"),
            ("medium", "متوسط"),
            ("hard", "متقدم"),
        ],
        default="medium",
    )

    publication_status = SelectField(
        "حالة الورقة",
        choices=[
            ("draft", "مسودة"),
            ("published", "منشورة"),
        ],
        default="draft",
    )

    allow_download = BooleanField(
        "السماح للطالب بتنزيل الملف",
        default=True,
    )

    worksheet_file = FileField(
        "ملف ورقة العمل",
        validators=[
            FileRequired(
                message="يرجى اختيار ملف."
            ),
            FileAllowed(
                [
                    "pdf",
                    "doc",
                    "docx",
                    "png",
                    "jpg",
                    "jpeg",
                ],
                message=(
                    "الصيغ المسموحة: "
                    "PDF وWord والصور."
                ),
            ),
        ],
    )
    
    answer_key_file = FileField(
    "نموذج الإجابة — اختياري",
    validators=[
        Optional(),
        FileAllowed(
            [
                "pdf",
                "doc",
                "docx",
                "png",
                "jpg",
                "jpeg",
            ],
            "صيغة نموذج الإجابة غير مسموحة.",
        ),
    ],
    )

    submit = SubmitField(
        "حفظ ورقة العمل"
    )
    
class EditWorksheetForm(FlaskForm):
    lesson_id = SelectField(
        "الدرس",
        coerce=int,
        validators=[
            DataRequired(
                message="يرجى اختيار الدرس."
            )
        ],
    )

    title = StringField(
        "عنوان ورقة العمل",
        validators=[
            DataRequired(
                message="يرجى كتابة العنوان."
            ),
            Length(max=250),
        ],
    )

    description = TextAreaField(
        "وصف الورقة",
        validators=[
            Length(max=2000)
        ],
    )

    instructions = TextAreaField(
        "تعليمات الطالب",
        validators=[
            Length(max=2000)
        ],
    )

    difficulty_level = SelectField(
        "مستوى الصعوبة",
        choices=[
            ("easy", "سهل"),
            ("medium", "متوسط"),
            ("hard", "متقدم"),
        ],
    )

    publication_status = SelectField(
        "حالة الورقة",
        choices=[
            ("draft", "مسودة"),
            ("published", "منشورة"),
        ],
    )

    allow_download = BooleanField(
        "السماح بتنزيل الملف"
    )

    submit = SubmitField(
        "حفظ التعديلات"
    )