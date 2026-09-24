from urllib.parse import urljoin, urlparse

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import (
    current_user,
    login_required,
    login_user,
    logout_user,
)

from alrayyan.extensions import db
from alrayyan.forms import (
    AccountSettingsForm,
    LoginForm,
)
from alrayyan.models import User


auth_bp = Blueprint(
    "auth",
    __name__,
    url_prefix="/auth",
)


def is_safe_redirect_url(target):
    """
    Prevent redirecting users to an external website
    after logging in.
    """
    if not target:
        return False

    host_url = urlparse(
        request.host_url
    )

    redirect_url = urlparse(
        urljoin(
            request.host_url,
            target,
        )
    )

    return (
        redirect_url.scheme
        in {"http", "https"}
        and host_url.netloc
        == redirect_url.netloc
    )


def get_user_homepage(user):
    """
    Send each user to the correct page
    according to their role.
    """
    if user.role in {
        "teacher",
        "admin",
    }:
        return url_for(
            "teacher_dashboard.dashboard"
        )

    return url_for(
    "main.student_dashboard"
    )


@auth_bp.route(
    "/login",
    methods=["GET", "POST"],
)
def login():
    if current_user.is_authenticated:
        return redirect(
            get_user_homepage(
                current_user
            )
        )

    form = LoginForm()

    if form.validate_on_submit():
        email = (
            form.email.data
            .strip()
            .lower()
        )

        user = User.query.filter_by(
            email=email,
        ).first()

        if (
            not user
            or not user.check_password(
                form.password.data
            )
        ):
            flash(
                (
                    "البريد الإلكتروني أو "
                    "كلمة المرور غير صحيحة."
                ),
                "error",
            )

            return render_template(
                "login.html",
                form=form,
            )

        if not user.is_active_account:
            flash(
                "هذا الحساب غير نشط حاليًا.",
                "error",
            )

            return render_template(
                "login.html",
                form=form,
            )

        login_user(
            user,
            remember=form.remember.data,
        )

        flash(
            f"أهلًا بكِ {user.full_name}.",
            "success",
        )

        next_page = request.args.get(
            "next"
        )

        if is_safe_redirect_url(
            next_page
        ):
            return redirect(
                next_page
            )

        return redirect(
            get_user_homepage(user)
        )

    return render_template(
        "login.html",
        form=form,
    )


@auth_bp.post("/logout")
def logout():
    if current_user.is_authenticated:
        logout_user()

    return redirect(
        url_for("main.home")
    )


@auth_bp.route(
    "/account/",
    methods=["GET", "POST"],
)
@login_required
def account_settings():
    """Display and update the signed-in user's account."""

    form = AccountSettingsForm(
        obj=current_user
    )

    if form.validate_on_submit():
        normalized_email = (
            form.email.data
            .strip()
            .lower()
        )

        duplicate_user = (
            User.query
            .filter(
                User.email == normalized_email,
                User.id != current_user.id,
            )
            .first()
        )

        if duplicate_user:
            form.email.errors.append(
                "هذا البريد مستخدم في حساب آخر."
            )
        elif (
            form.new_password.data
            and not form.current_password.data
        ):
            form.current_password.errors.append(
                "اكتبي كلمة المرور الحالية أولًا."
            )
        elif (
            form.new_password.data
            and not current_user.check_password(
                form.current_password.data
            )
        ):
            form.current_password.errors.append(
                "كلمة المرور الحالية غير صحيحة."
            )
        else:
            current_user.full_name = (
                form.full_name.data.strip()
            )
            current_user.email = normalized_email

            if form.new_password.data:
                current_user.set_password(
                    form.new_password.data
                )

            db.session.commit()

            flash(
                "تم تحديث بيانات حسابك بنجاح.",
                "success",
            )

            return redirect(
                url_for(
                    "auth.account_settings"
                )
            )

    return render_template(
        "account_settings.html",
        form=form,
    )
