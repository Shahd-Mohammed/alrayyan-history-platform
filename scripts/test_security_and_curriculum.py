"""Regression checks for admin authorization, password reset, and curriculum data safety."""

import os
import tempfile
from datetime import datetime, timezone

db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
db_file.close()
os.environ["DATABASE_URL"] = f"sqlite:///{db_file.name}"

from app import app  # noqa: E402
from alrayyan.extensions import db  # noqa: E402
from alrayyan.models import (  # noqa: E402
    CharacterAttempt,
    Curriculum,
    HistoricalCharacter,
    Lesson,
    Unit,
    Worksheet,
    User,
)
from alrayyan.routes.auth import _password_reset_serializer  # noqa: E402

app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

with app.app_context():
    db.create_all()
    teacher = User(full_name="معلمة تجريبية", email="teacher@example.com", role="teacher")
    teacher.set_password("teacher-password-123")
    admin = User(full_name="مديرة تجريبية", email="admin@example.com", role="admin")
    admin.set_password("admin-password-123")
    student = User(full_name="طالبة تجريبية", email="student@example.com", role="student")
    student.set_password("student-password-123")
    db.session.add_all([teacher, admin, student])
    db.session.flush()

    curriculum = Curriculum(
        created_by_id=teacher.id,
        name="منهج حذف تجريبي",
        subject="تاريخ",
        grade="11",
        semester="1",
        academic_year="2026",
        version="delete-test",
    )
    db.session.add(curriculum)
    db.session.flush()
    unit = Unit(curriculum_id=curriculum.id, title="وحدة", order_index=1)
    db.session.add(unit)
    db.session.flush()
    lesson = Lesson(unit_id=unit.id, title="درس", slug="security-delete-test", order_index=1)
    db.session.add(lesson)
    db.session.flush()
    character = HistoricalCharacter(
        lesson_id=lesson.id,
        name="شخصية تجريبية",
        summary="ملخص تجريبي",
        publication_status="published",
    )
    db.session.add(character)
    db.session.flush()
    attempt = CharacterAttempt(
        character_id=character.id,
        student_id=student.id,
        answer_text="إجابة",
        is_correct=True,
        xp_awarded=5,
        attempted_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.session.add(attempt)
    # A separate curriculum with an unused worksheet should remain deletable.
    clean_curriculum = Curriculum(
        created_by_id=teacher.id,
        name="منهج بلا محاولات",
        subject="تاريخ",
        grade="11",
        semester="2",
        academic_year="2026",
        version="unused-test",
    )
    db.session.add(clean_curriculum)
    db.session.flush()
    clean_unit = Unit(curriculum_id=clean_curriculum.id, title="وحدة فارغة", order_index=1)
    db.session.add(clean_unit)
    db.session.flush()
    clean_lesson = Lesson(
        unit_id=clean_unit.id,
        title="درس بلا محاولات",
        slug="security-clean-delete-test",
        order_index=1,
    )
    db.session.add(clean_lesson)
    db.session.flush()
    clean_worksheet = Worksheet(
        lesson_id=clean_lesson.id,
        created_by_id=teacher.id,
        title="اختبار بلا محاولات",
        publication_status="draft",
        is_published=False,
    )
    db.session.add(clean_worksheet)
    ids = {
        "teacher": teacher.id,
        "admin": admin.id,
        "student": student.id,
        "curriculum": curriculum.id,
        "character": character.id,
        "clean_curriculum": clean_curriculum.id,
    }
    token = _password_reset_serializer().dumps(
        {"user_id": student.id, "email": student.email},
        salt="alrayyan-password-reset",
    )
    db.session.commit()

client = app.test_client()

def login_as(user_id):
    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True

# A teacher cannot open the administrator-account management page.
login_as(ids["teacher"])
response = client.get("/teacher-dashboard/platform/admins")
assert response.status_code == 403

# Deleting a curriculum must not cascade-delete character attempts or student XP history.
response = client.post(f"/teacher-dashboard/platform/curricula/{ids['curriculum']}/delete")
assert response.status_code == 302
with app.app_context():
    assert db.session.get(Curriculum, ids["curriculum"]) is not None
    assert db.session.query(CharacterAttempt).filter_by(
        character_id=ids["character"]
    ).first() is not None

# Unused content (including a worksheet without attempts) can be removed for a new term.
response = client.post(f"/teacher-dashboard/platform/curricula/{ids['clean_curriculum']}/delete")
assert response.status_code == 302
with app.app_context():
    assert db.session.get(Curriculum, ids["clean_curriculum"]) is None

# Only an administrator can create another administrator, and duplicates are rejected.
login_as(ids["admin"])
response = client.post(
    "/teacher-dashboard/platform/admins",
    data={
        "full_name": "مديرة ثانية",
        "email": "admin2@example.com",
        "password": "new-admin-password-123",
    },
)
assert response.status_code == 302
with app.app_context():
    created = User.query.filter_by(email="admin2@example.com").first()
    assert created is not None and created.role == "admin"
response = client.post(
    "/teacher-dashboard/platform/admins",
    data={
        "full_name": "مديرة ثانية",
        "email": "admin2@example.com",
        "password": "new-admin-password-123",
    },
)
assert response.status_code == 200

# Password-reset tokens are time-limited/signed; valid tokens update the password.
response = client.post(
    f"/auth/reset-password/{token}",
    data={"password": "student-new-password-123", "confirm_password": "student-new-password-123"},
)
assert response.status_code == 302
with app.app_context():
    student = db.session.get(User, ids["student"])
    assert student.check_password("student-new-password-123")

response = client.get("/auth/reset-password/not-a-valid-token")
assert response.status_code == 302

print("PASS: admin authorization/creation, password reset, and curriculum history protection")
