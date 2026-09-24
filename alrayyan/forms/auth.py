from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    PasswordField,
    StringField,
    SubmitField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    Length,
    Optional,
)


class LoginForm(FlaskForm):
    email = StringField(
        "البريد الإلكتروني",
        validators=[
            DataRequired(
                message="يرجى كتابة البريد الإلكتروني."
            ),
            Length(
                max=255,
                message="البريد الإلكتروني طويل جدًا.",
            ),
        ],
    )

    password = PasswordField(
        "كلمة المرور",
        validators=[
            DataRequired(
                message="يرجى كتابة كلمة المرور."
            ),
            Length(
                min=8,
                max=128,
                message=(
                    "كلمة المرور يجب أن تحتوي "
                    "على 8 أحرف على الأقل."
                ),
            ),
        ],
    )

    remember = BooleanField(
        "تذكرني"
    )

    submit = SubmitField(
        "تسجيل الدخول"
    )


class AccountSettingsForm(FlaskForm):
    """Allow a signed-in user to edit account details."""

    full_name = StringField(
        "الاسم الكامل",
        validators=[
            DataRequired(
                message="يرجى كتابة الاسم الكامل."
            ),
            Length(
                min=2,
                max=150,
                message=(
                    "يجب أن يكون الاسم بين "
                    "حرفين و150 حرفًا."
                ),
            ),
        ],
    )

    email = StringField(
        "البريد الإلكتروني",
        validators=[
            DataRequired(
                message="يرجى كتابة البريد الإلكتروني."
            ),
            Email(
                message="يرجى كتابة بريد إلكتروني صالح."
            ),
            Length(max=255),
        ],
    )

    current_password = PasswordField(
        "كلمة المرور الحالية",
        validators=[
            Optional(),
            Length(min=8, max=128),
        ],
    )

    new_password = PasswordField(
        "كلمة المرور الجديدة",
        validators=[
            Optional(),
            Length(
                min=8,
                max=128,
                message=(
                    "كلمة المرور الجديدة يجب أن "
                    "تحتوي على 8 أحرف على الأقل."
                ),
            ),
        ],
    )

    confirm_password = PasswordField(
        "تأكيد كلمة المرور الجديدة",
        validators=[
            Optional(),
            EqualTo(
                "new_password",
                message="كلمتا المرور غير متطابقتين.",
            ),
        ],
    )

    submit = SubmitField(
        "حفظ التغييرات"
    )
