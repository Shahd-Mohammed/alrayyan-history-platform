"""Grade-based access checks for student-facing learning content.

Curriculum.grade is the source of truth for content grade. A student's grade is
derived from their active classroom enrollment, so this adds no risky data
migration and keeps existing enrollment records intact.
"""
import re

from flask import request, session

from alrayyan.models import ClassEnrollment, Classroom, Curriculum, Lesson, Unit
from alrayyan.extensions import db


_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def normalize_grade(value):
    text = (value or "").translate(_ARABIC_DIGITS).strip().casefold()
    compact = re.sub(r"[\sـ_\-()\[\]{}]+", "", text)
    if re.search(r"(?:الحاديعشر|الحاديةعشرة|grade11|year11|(?<!\d)11(?!\d))", compact):
        return "11"
    if re.search(r"(?:الثانيعشر|الثانيةعشرة|grade12|year12|(?<!\d)12(?!\d))", compact):
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

def selected_management_grade():
    """Remember the teacher's selected grade for all management pages."""
    from flask_login import current_user

    if not current_user.is_authenticated or current_user.role not in {"teacher", "admin"}:
        return None

    requested = normalize_grade(request.args.get("grade"))
    if requested in {"11", "12"}:
        session["teacher_selected_grade"] = requested

    selected = normalize_grade(session.get("teacher_selected_grade"))
    if selected not in {"11", "12"}:
        selected = None
        try:
            from flask_login import current_user
            if current_user.is_authenticated and current_user.role in {"teacher", "admin"}:
                teacher_id = current_user.id if current_user.role == "teacher" else None
                grades_query = db.session.query(Classroom.grade).filter(Classroom.is_active.is_(True))
                if teacher_id is not None:
                    grades_query = grades_query.filter(Classroom.teacher_id == teacher_id)
                available = {normalize_grade(row[0]) for row in grades_query.all()}
                available.discard(None)
                if "11" in available:
                    selected = "11"
                elif "12" in available:
                    selected = "12"
        except Exception:
            selected = None
        selected = selected or "11"
        session["teacher_selected_grade"] = selected
    return selected


def lesson_ids_for_grade(grade):
    """Return lesson IDs whose owning curriculum matches the requested grade."""
    normalized = normalize_grade(grade)
    if normalized not in {"11", "12"}:
        return []
    rows = (
        db.session.query(Lesson.id, Curriculum.grade)
        .join(Unit, Unit.id == Lesson.unit_id)
        .join(Curriculum, Curriculum.id == Unit.curriculum_id)
        .all()
    )
    return [lesson_id for lesson_id, row_grade in rows if normalize_grade(row_grade) == normalized]


def curriculum_ids_for_grade(grade):
    """Return curriculum IDs for one normalized grade."""
    normalized = normalize_grade(grade)
    if normalized not in {"11", "12"}:
        return []
    rows = db.session.query(Curriculum.id, Curriculum.grade).all()
    return [curriculum_id for curriculum_id, row_grade in rows if normalize_grade(row_grade) == normalized]


def classroom_ids_for_grade(grade, teacher_id=None, active_only=True):
    """Return classroom IDs in one grade, optionally for one teacher."""
    normalized = normalize_grade(grade)
    if normalized not in {"11", "12"}:
        return []
    query = db.session.query(Classroom.id, Classroom.grade)
    if active_only:
        query = query.filter(Classroom.is_active.is_(True))
    if teacher_id is not None:
        query = query.filter(Classroom.teacher_id == teacher_id)
    rows = query.all()
    return [classroom_id for classroom_id, row_grade in rows if normalize_grade(row_grade) == normalized]


def student_ids_for_grade(grade, teacher_id=None, active_only=True):
    """Return students assigned exclusively to one grade."""
    normalized = normalize_grade(grade)
    classroom_ids = classroom_ids_for_grade(
        grade, teacher_id=teacher_id, active_only=active_only
    )
    if normalized not in {"11", "12"} or not classroom_ids:
        return []

    target_student_ids = {
        student_id for (student_id,) in
        db.session.query(ClassEnrollment.student_id)
        .filter(ClassEnrollment.classroom_id.in_(classroom_ids))
        .distinct().all()
    }
    if not target_student_ids:
        return []

    # Check each target student's full active enrollment history, not only the
    # currently selected teacher's classrooms, to catch cross-teacher conflicts.
    rows = (
        db.session.query(ClassEnrollment.student_id, Classroom.grade)
        .join(Classroom, Classroom.id == ClassEnrollment.classroom_id)
        .filter(
            Classroom.is_active.is_(True),
            ClassEnrollment.student_id.in_(target_student_ids),
        )
        .all()
    )
    grades_by_student = {}
    for student_id, row_grade in rows:
        grades_by_student.setdefault(student_id, set()).add(normalize_grade(row_grade))

    # Exclude conflicting active-grade assignments from both workspaces.
    return [
        student_id for student_id in target_student_ids
        if grades_by_student.get(student_id) == {normalized}
    ]

