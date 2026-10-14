"""Regression tests for automatic/manual grading and idempotent XP awards."""

import os
import tempfile
from datetime import datetime, timezone

db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
db_file.close()
os.environ["DATABASE_URL"] = f"sqlite:///{db_file.name}"

from app import app  # noqa: E402
from alrayyan.extensions import db  # noqa: E402
from alrayyan.models import (  # noqa: E402
    Curriculum,
    Lesson,
    Question,
    StudentAnswer,
    Unit,
    User,
    Worksheet,
    WorksheetAttempt,
    XPTransaction,
)
from alrayyan.routes.assessment import calculate_attempt_result  # noqa: E402

app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

with app.app_context():
    db.create_all()
    teacher = User(full_name="معلمة العلامات", email="grading-teacher@example.com", role="teacher")
    teacher.set_password("teacher-password-123")
    student = User(full_name="طالبة العلامات", email="grading-student@example.com", role="student")
    student.set_password("student-password-123")
    db.session.add_all([teacher, student])
    db.session.flush()

    curriculum = Curriculum(
        created_by_id=teacher.id,
        name="منهج العلامات",
        subject="تاريخ",
        grade="11",
        semester="1",
        academic_year="2026",
        version="grading-test",
    )
    db.session.add(curriculum)
    db.session.flush()
    unit = Unit(curriculum_id=curriculum.id, title="وحدة", order_index=1)
    db.session.add(unit)
    db.session.flush()
    lesson = Lesson(unit_id=unit.id, title="درس العلامات", slug="grading-test-lesson", order_index=1)
    db.session.add(lesson)
    db.session.flush()
    worksheet = Worksheet(
        lesson_id=lesson.id,
        created_by_id=teacher.id,
        title="اختبار العلامات",
        creation_method="test",
        passing_score=50,
        publication_status="published",
        is_published=True,
    )
    db.session.add(worksheet)
    db.session.flush()
    auto_question = Question(
        worksheet_id=worksheet.id,
        question_text="سؤال آلي",
        question_type="multiple_choice",
        correct_answer_text="أ",
        points=5,
        order_index=1,
    )
    essay_question = Question(
        worksheet_id=worksheet.id,
        question_text="سؤال مقالي",
        question_type="essay",
        correct_answer_text=None,
        points=10,
        requires_manual_grading=True,
        order_index=2,
    )
    db.session.add_all([auto_question, essay_question])
    db.session.flush()
    attempt = WorksheetAttempt(
        worksheet_id=worksheet.id,
        student_id=student.id,
        submitted_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.session.add(attempt)
    db.session.flush()
    db.session.add_all([
        StudentAnswer(
            attempt_id=attempt.id,
            question_id=auto_question.id,
            answer_text="أ",
            is_correct=True,
            awarded_points=5,
        ),
        StudentAnswer(
            attempt_id=attempt.id,
            question_id=essay_question.id,
            answer_text="إجابة مقالية",
            is_correct=None,
            awarded_points=0,
        ),
    ])
    db.session.flush()
    attempt_id, student_id, essay_answer_id = attempt.id, student.id, None
    essay_answer_id = StudentAnswer.query.filter_by(
        attempt_id=attempt.id, question_id=essay_question.id
    ).first().id

    # Pending manual grading must not mark the attempt passed or award XP.
    calculate_attempt_result(attempt)
    assert attempt.score == 5
    assert attempt.max_score == 15
    assert attempt.is_passed is False
    assert XPTransaction.query.filter_by(source_id=attempt.id, source_type="worksheet_attempt").count() == 0

    # First manual grade finalizes the result and awards points once.
    essay_answer = db.session.get(StudentAnswer, essay_answer_id)
    essay_answer.awarded_points = 6
    essay_answer.is_correct = False
    essay_answer.graded_at = datetime.now(timezone.utc).replace(tzinfo=None)
    calculate_attempt_result(attempt)
    db.session.commit()
    assert attempt.score == 11
    assert round(attempt.percentage, 2) == round(11 / 15 * 100, 2)
    award = XPTransaction.query.filter_by(
        student_id=student_id,
        source_type="worksheet_attempt",
        source_id=attempt_id,
    ).one()
    assert award.amount == 16
    student = db.session.get(User, student_id)
    assert student.points == 16

    # A revised manual grade adjusts the existing award, never duplicates it.
    essay_answer.awarded_points = 8
    calculate_attempt_result(attempt)
    db.session.commit()
    award = XPTransaction.query.filter_by(
        student_id=student_id,
        source_type="worksheet_attempt",
        source_id=attempt_id,
    ).one()
    assert award.amount == 18
    assert XPTransaction.query.filter_by(
        student_id=student_id,
        source_type="worksheet_attempt",
        source_id=attempt_id,
    ).count() == 1
    assert student.points == 18
    assert attempt.score == 13

print("PASS: pending manual grading, score calculation, and XP updates after regrading")
