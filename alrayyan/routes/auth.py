from datetime import datetime, timezone
from email.message import EmailMessage
import re
import smtplib
from urllib.parse import urljoin, urlparse

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from flask_login import (
    current_user,
    login_required,
    login_user,
    logout_user,
)

from alrayyan.extensions import db
from alrayyan.forms import (
    AccountSettingsForm,
    InvitationRegistrationForm,
    LoginForm,
)
from alrayyan.models import ClassEnrollment, StudentInvitation, User


auth_bp = Blueprint(
    "auth",
    __name__,
    url_prefix="/auth",
)


@auth_bp.route("/join/<token>", methods=["GET", "POST"])
def register_invitation(token):
    if current_user.is_authenticated:
        return redirect(get_user_homepage(current_user))
    invitation = StudentInvitation.find_valid(token)
    if invitation is None:
        return render_template("invitation_invalid.html"), 410
    form = InvitationRegistrationForm()
    if form.validate_on_submit():
        if User.query.filter_by(email=invitation.email).first():
            flash("هذا البريد مستخدم مسبقًا", "error")
        else:
            user = User(full_name=form.full_name.data.strip(), email=invitation.email, role="student", is_active_account=True)
            user.set_password(form.password.data)
            db.session.add(user); db.session.flush()
            if invitation.classroom_id:
                db.session.add(ClassEnrollment(classroom_id=invitation.classroom_id, student_id=user.id))
            invitation.accepted_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.session.commit(); login_user(user)
            return redirect(url_for("main.student_dashboard"))
    return render_template("invitation_register.html", form=form, invitation=invitation)


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


def _password_reset_serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])


def _send_password_reset_email(user, reset_url):
    host = current_app.config.get("SMTP_HOST")
    username = current_app.config.get("SMTP_USERNAME")
    password = current_app.config.get("SMTP_PASSWORD")
    sender = current_app.config.get("SMTP_FROM_EMAIL")
    if not all((host, username, password, sender)):
        current_app.logger.warning("Password reset email is not configured: SMTP settings are incomplete.")
        return False

    message = EmailMessage()
    message["Subject"] = "إعادة تعيين كلمة مرور منصة الريان"
    message["From"] = sender
    message["To"] = user.email
    message.set_content(
        f"مرحبًا {user.first_name}،\n\n"
        "وصلنا طلب لإعادة تعيين كلمة المرور لحسابك في منصة الريان. "
        "إذا لم تطلبي ذلك، تجاهلي هذه الرسالة.\n\n"
        f"افتحي الرابط التالي خلال 30 دقيقة لإعادة التعيين:\n{reset_url}\n\n"
        "لأمان حسابك، لا تشاركي هذا الرابط مع أي شخص."
    )

    with smtplib.SMTP(
        host,
        int(current_app.config.get("SMTP_PORT", 587)),
        timeout=20,
    ) as server:
        if current_app.config.get("SMTP_USE_TLS", True):
            server.starttls()
        server.login(username, password)
        server.send_message(message)
    return True


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(get_user_homepage(current_user))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        user = User.query.filter_by(email=email).first() if email else None
        if user and user.is_active_account:
            token = _password_reset_serializer().dumps(
                {"user_id": user.id, "email": user.email},
                salt="alrayyan-password-reset",
            )
            public_base_url = (current_app.config.get("PUBLIC_BASE_URL") or "").strip().rstrip("/")
            if not public_base_url:
                current_app.logger.error(
                    "Password reset email skipped: PUBLIC_BASE_URL is not configured."
                )
            else:
                reset_path = url_for("auth.reset_password", token=token)
                reset_url = urljoin(public_base_url + "/", reset_path.lstrip("/"))
                try:
                    _send_password_reset_email(user, reset_url)
                except Exception:
                    current_app.logger.exception("Unable to send a password reset email.")
        flash(
            "إذا كان البريد مسجّلًا ونشطًا، فستصلك رسالة تتضمن رابط إعادة التعيين خلال دقائق.",
            "info",
        )
        return redirect(url_for("auth.forgot_password"))

    return render_template("forgot_password.html")


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    try:
        payload = _password_reset_serializer().loads(
            token,
            salt="alrayyan-password-reset",
            max_age=1800,
        )
        user = User.query.filter_by(
            id=payload.get("user_id"),
            email=payload.get("email"),
        ).first()
    except (BadSignature, SignatureExpired, AttributeError, TypeError, ValueError):
        user = None

    if user is None or not user.is_active_account:
        flash("رابط إعادة التعيين غير صالح أو انتهت صلاحيته. اطلبي رابطًا جديدًا.", "error")
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":
        password = request.form.get("password") or ""
        confirmation = request.form.get("confirm_password") or ""
        if len(password) < 12 or len(password) > 128:
            flash("اختاري كلمة مرور من 12 إلى 128 حرفًا.", "error")
        elif password != confirmation:
            flash("كلمتا المرور غير متطابقتين.", "error")
        else:
            user.set_password(password)
            db.session.commit()
            flash("تم تغيير كلمة المرور بنجاح. سجّلي الدخول بكلمة المرور الجديدة.", "success")
            return redirect(url_for("auth.login"))

    return render_template("reset_password.html", token=token)


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

        email_is_valid = bool(re.fullmatch(r"[^@\s]+@[^@\s]+(?:\.[^@\s]+)?", normalized_email))
        duplicate_user = (
            User.query
            .filter(
                User.email == normalized_email,
                User.id != current_user.id,
            )
            .first()
        )

        if not email_is_valid:
            form.email.errors.append("يرجى كتابة بريد إلكتروني صالح.")
        elif duplicate_user:
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
