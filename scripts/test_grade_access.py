"""Regression checks for grade-specific lesson access without migrating student data."""

import os
import tempfile

db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
db_file.close()
os.environ["DATABASE_URL"] = f"sqlite:///{db_file.name}"

from app import app  # noqa: E402
from alrayyan.extensions import db  # noqa: E402
from alrayyan.models import ClassEnrollment, Classroom, Curriculum, Lesson, Unit, User  # noqa: E402
from alrayyan.services.grade_access import (  # noqa: E402
    lessons_for_user,
    normalize_grade,
    student_can_access_lesson,
    student_grade,
)

app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

assert normalize_grade("الصف الحادي عشر") == "11"
assert normalize_grade("الصف الثاني عشر") == "12"
assert normalize_grade("Grade 11") == "11"
assert normalize_grade("الصف ١٢") == "12"
assert normalize_grade("العام الدراسي 2025-2026") is None
assert normalize_grade("2011") is None

with app.app_context():
    db.create_all()
    teacher = User(full_name="معلمة الصفوف", email="grade-teacher@example.com", role="teacher")
    grade11_student = User(full_name="طالبة الحادي عشر", email="grade11-student@example.com", role="student")
    grade12_student = User(full_name="طالبة الثاني عشر", email="grade12-student@example.com", role="student")
    unassigned_student = User(full_name="طالبة بلا صف", email="unassigned-student@example.com", role="student")
    mixed_student = User(full_name="طالبة ذات تسجيلين", email="mixed-student@example.com", role="student")
    db.session.add_all([teacher, grade11_student, grade12_student, unassigned_student, mixed_student])
    db.session.flush()

    def add_lesson(grade, suffix):
        curriculum = Curriculum(
            created_by_id=teacher.id,
            name=f"منهج الصف {grade} {suffix}",
            subject="تاريخ",
            grade=grade,
            semester="1",
            academic_year="2026",
            version=f"grade-access-{suffix}",
            is_active=True,
            processing_status="ready",
        )
        db.session.add(curriculum)
        db.session.flush()
        unit = Unit(curriculum_id=curriculum.id, title=f"وحدة {suffix}", order_index=1)
        db.session.add(unit)
        db.session.flush()
        lesson = Lesson(
            unit_id=unit.id,
            title=f"درس {suffix}",
            slug=f"grade-access-{suffix}",
            order_index=1,
            is_published=True,
        )
        db.session.add(lesson)
        db.session.flush()
        return lesson

    lesson11 = add_lesson("الصف الحادي عشر", "eleven")
    lesson12 = add_lesson("الصف الثاني عشر", "twelve")

    class11 = Classroom(
        teacher_id=teacher.id,
        name="الحادي عشر",
        grade="الصف الحادي عشر",
        academic_year="2026",
        is_active=True,
    )
    class12 = Classroom(
        teacher_id=teacher.id,
        name="الثاني عشر",
        grade="الصف الثاني عشر",
        academic_year="2026",
        is_active=True,
    )
    db.session.add_all([class11, class12])
    db.session.flush()
    db.session.add_all([
        ClassEnrollment(classroom_id=class11.id, student_id=grade11_student.id),
        ClassEnrollment(classroom_id=class12.id, student_id=grade12_student.id),
        ClassEnrollment(classroom_id=class11.id, student_id=mixed_student.id),
        ClassEnrollment(classroom_id=class12.id, student_id=mixed_student.id),
    ])
    db.session.commit()

    assert student_grade(grade11_student) == "11"
    assert student_grade(grade12_student) == "12"
    assert student_grade(unassigned_student) is None
    assert student_grade(mixed_student) is None

    visible11 = set(lessons_for_user(grade11_student))
    visible12 = set(lessons_for_user(grade12_student))
    assert lesson11.id in visible11 and lesson12.id not in visible11
    assert lesson12.id in visible12 and lesson11.id not in visible12
    assert lessons_for_user(unassigned_student) == []
    assert lessons_for_user(mixed_student) == []

    assert student_can_access_lesson(grade11_student, lesson11)
    assert not student_can_access_lesson(grade11_student, lesson12)
    assert student_can_access_lesson(grade12_student, lesson12)
    assert not student_can_access_lesson(grade12_student, lesson11)

print("PASS: grade normalization, classroom assignment, and cross-grade access denial")
