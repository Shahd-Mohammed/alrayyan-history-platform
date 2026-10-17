"""Grade-based access checks for student-facing learning content.

Curriculum.grade is the source of truth for content grade. A student's grade is
derived from their active classroom enrollment, so this adds no risky data
migration and keeps existing enrollment records intact.
"""
import re

from alrayyan.models import ClassEnrollment, Classroom, Curriculum, Lesson, Unit
from alrayyan.extensions import db


_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def normalize_grade(value):
    text = (value or "").translate(_ARABIC_DIGITS).strip().casefold()
    compact = re.sub(r"[\sـ_\-()\[\]{}]+", "", text)
    if re.search(r"(?:الحاديعشر|الحاديةعشرة|grade11|year11|11)", compact):
        return "11"
    if re.search(r"(?:الثانيعشر|الثانيةعشرة|grade12|year12|12)", compact):
        return "12"
    return None


def student_grade(user):
    """Return one unambiguous grade, or None when the student is unassigned."""
    if not user or user.role != "student":
        return None
    rows = (
        db.session.query(Classroom.grade)
        .join(ClassEnrollment, ClassEnrollment.classroom_id == Classroom.id)
        .filter(
            ClassEnrollment.student_id == user.id,
            Classroom.is_active.is_(True),
        )
        .all()
    )
    grades = {normalize_grade(row[0]) for row in rows}
    grades.discard(None)
    return next(iter(grades)) if len(grades) == 1 else None


def lessons_for_user(user, active_only=True):
    """Return lesson IDs visible to this user; students fail closed if unassigned."""
    query = (
        db.session.query(Lesson.id, Curriculum.grade, Curriculum.is_active)
        .join(Unit, Unit.id == Lesson.unit_id)
        .join(Curriculum, Curriculum.id == Unit.curriculum_id)
    )
    if active_only:
        query = query.filter(Curriculum.is_active.is_(True))
    rows = query.all()
    if not user or user.role != "student":
        return [row[0] for row in rows]
    grade = student_grade(user)
    if grade is None:
        return []
    return [row[0] for row in rows if normalize_grade(row[1]) == grade]


def student_can_access_lesson(user, lesson):
    """Check grade authorization for a direct lesson/content URL."""
    if not user or user.role != "student":
        return True
    if lesson is None or lesson.unit is None or lesson.unit.curriculum is None:
        return False
    grade = student_grade(user)
    return grade is not None and normalize_grade(lesson.unit.curriculum.grade) == grade
