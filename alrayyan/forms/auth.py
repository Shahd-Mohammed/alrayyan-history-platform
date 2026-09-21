from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    PasswordField,
    StringField,
    SubmitField,
)
from wtforms.validators import (
    DataRequired,
    Length,
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