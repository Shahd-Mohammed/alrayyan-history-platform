from flask import (
    Blueprint,
    abort,
    redirect,
    render_template,
    url_for,
)

from flask_login import (
    current_user,
    login_required,
)

from alrayyan.models import (
    Worksheet,
    WorksheetAttempt,
)


main_bp = Blueprint(
    "main",
    __name__,
)


@main_bp.get("/")
def home():
    return render_template(
        "home.html"
    )


@main_bp.get("/student-dashboard/")
@login_required
def student_dashboard():
    """
    Display the student's learning dashboard.
    """

    if current_user.role in {
        "teacher",
        "admin",
    }:
        return redirect(
            url_for(
                "teacher_dashboard.dashboard"
            )
        )

    if current_user.role != "student":
        abort(403)

    available_worksheets = (
        Worksheet.query
        .filter_by(
            publication_status="published",
            is_published=True,
        )
        .order_by(
            Worksheet.created_at.desc()
        )
        .all()
    )

    open_attempts = (
        WorksheetAttempt.query
        .filter_by(
            student_id=current_user.id,
            submitted_at=None,
        )
        .order_by(
            WorksheetAttempt.started_at.desc()
        )
        .all()
    )

    completed_attempts = (
        WorksheetAttempt.query
        .filter_by(
            student_id=current_user.id,
        )
        .filter(
            WorksheetAttempt
            .submitted_at
            .isnot(None)
        )
        .order_by(
            WorksheetAttempt
            .submitted_at
            .desc()
        )
        .all()
    )

    latest_results = (
        completed_attempts[:3]
    )

    return render_template(
        "student_dashboard.html",
        available_worksheets=(
            available_worksheets
        ),
        open_attempts=open_attempts,
        completed_attempts=(
            completed_attempts
        ),
        latest_results=latest_results,
    )