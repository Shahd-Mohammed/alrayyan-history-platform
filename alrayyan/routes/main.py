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
from sqlalchemy import text

from alrayyan.extensions import db

from alrayyan.models import (
    AboutPage,
    ConceptMap,
    ContentChunk,
    Curriculum,
    HistoricalCharacter,
    LearningResource,
    Lesson,
    Worksheet,
    WorksheetAttempt,
)


main_bp = Blueprint(
    "main",
    __name__,
)


@main_bp.get("/health")
def health():
    """Small deployment health check without exposing private data."""
    db.session.execute(text("SELECT 1"))
    return {"status": "ok"}, 200


@main_bp.get("/")
def home():
    featured_worksheets = (
        Worksheet.query
        .filter_by(
            publication_status="published",
            is_published=True,
            is_archived=False,
        )
        .order_by(
            Worksheet.created_at.desc()
        )
        .limit(5)
        .all()
    )

    public_stats = {
        "subjects": Curriculum.query.filter_by(is_active=True).with_entities(Curriculum.subject).distinct().count(),
        "lessons": Lesson.query.filter_by(is_published=True).count(),
        "knowledge_chunks": ContentChunk.query.count(),
        "activities": Worksheet.query.filter_by(publication_status="published", is_published=True, is_archived=False).count(),
        "learning_resources": LearningResource.query.filter_by(publication_status="published").count(),
        "maps": ConceptMap.query.filter_by(publication_status="published").count(),
        "characters": HistoricalCharacter.query.filter_by(publication_status="published").count(),
    }

    return render_template(
        "home.html",
        featured_worksheets=(
            featured_worksheets
        ),
        public_stats=public_stats,
    )


@main_bp.get("/about/")
def about():
    """Display the teacher and platform story."""

    about_content = (
        AboutPage.get_or_create()
    )

    return render_template(
        "about.html",
        about_content=about_content,
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
            is_archived=False,
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
