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
    CharacterAttempt,
    ChallengeSession,
    ConceptMap,
    ConceptMastery,
    ContentChunk,
    Curriculum,
    DateReview,
    HistoricalCharacter,
    HistoricalDate,
    LearningResource,
    Lesson,
    TutorConversation,
    TutorMessage,
    Worksheet,
    WorksheetAttempt,
    XPTransaction,
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

    published_query = Worksheet.query.filter_by(
        publication_status="published",
        is_published=True,
        is_archived=False,
    )
    available_worksheets = (
        published_query
        .filter(Worksheet.creation_method != "test")
        .order_by(Worksheet.created_at.desc())
        .all()
    )
    available_tests = (
        published_query
        .filter_by(creation_method="test")
        .order_by(Worksheet.created_at.desc())
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
        available_worksheets=available_worksheets,
        available_tests=available_tests,
        open_attempts=open_attempts,
        completed_attempts=(
            completed_attempts
        ),
        latest_results=latest_results,
    )



@main_bp.get("/student-progress/")
@login_required
def student_progress():
    """Show each student a private overview of their activity across the platform."""
    if current_user.role != "student":
        abort(403)

    attempts = (
        WorksheetAttempt.query
        .filter_by(student_id=current_user.id)
        .filter(WorksheetAttempt.submitted_at.isnot(None))
        .order_by(WorksheetAttempt.submitted_at.desc())
        .all()
    )
    tests_completed = sum(1 for item in attempts if item.worksheet and item.worksheet.creation_method == "test")
    worksheets_completed = sum(1 for item in attempts if item.worksheet and item.worksheet.creation_method != "test")

    challenge_sessions = ChallengeSession.query.filter_by(student_id=current_user.id).all()
    completed_challenges = sum(1 for item in challenge_sessions if item.status == "completed")
    masteries = (
        ConceptMastery.query.filter_by(student_id=current_user.id)
        .order_by(ConceptMastery.mastery_score.asc())
        .all()
    )
    tutor_conversations = TutorConversation.query.filter_by(student_id=current_user.id).count()
    tutor_evaluations = XPTransaction.query.filter_by(
        student_id=current_user.id,
        reason="tutor_evaluated_answer",
    ).count()
    character_attempts = CharacterAttempt.query.filter_by(student_id=current_user.id).count()
    date_reviews = DateReview.query.filter_by(student_id=current_user.id).count()
    points_by_reason = {}
    for transaction in (
        XPTransaction.query.filter_by(student_id=current_user.id)
        .order_by(XPTransaction.created_at.desc())
        .limit(100).all()
    ):
        points_by_reason[transaction.reason] = points_by_reason.get(transaction.reason, 0) + transaction.amount

    reason_labels = {
        "tutor_evaluated_answer": "إجابات قيّمها المعلّم الذكي",
        "challenge_answer": "إجابات التحديات",
        "challenge_completed": "إكمال التحديات",
        "character_identified": "التعرّف على الشخصيات",
        "concept_map_viewed": "استكشاف الخرائط المفاهيمية",
        "resource_downloaded": "تنزيل ملفات تعليمية",
        "test_completed": "إكمال الاختبارات",
        "worksheet_completed": "إكمال أوراق العمل",
        "historical_date_recalled": "مراجعة التواريخ التاريخية",
    }
    return render_template(
        "student_progress.html",
        attempts=attempts[:5],
        tests_completed=tests_completed,
        worksheets_completed=worksheets_completed,
        completed_challenges=completed_challenges,
        total_challenges=len(challenge_sessions),
        masteries=masteries,
        tutor_conversations=tutor_conversations,
        tutor_evaluations=tutor_evaluations,
        character_attempts=character_attempts,
        date_reviews=date_reviews,
        points_by_reason=points_by_reason,
        reason_labels=reason_labels,
    )
