"""Small integration test for worksheet visibility, archiving and timing."""

import os
import tempfile
from datetime import datetime, timedelta, timezone


database_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
database_file.close()
os.environ["DATABASE_URL"] = f"sqlite:///{database_file.name}"

from app import app  # noqa: E402
from alrayyan.extensions import db  # noqa: E402
from alrayyan.models import Curriculum, Lesson, Unit, User, Worksheet, WorksheetAttempt  # noqa: E402
from alrayyan.routes.assessment import get_remaining_seconds  # noqa: E402


app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

with app.app_context():
    db.create_all()
    teacher = User(full_name="معلمة الاختبار", email="teacher-test@example.com", role="teacher")
    teacher.set_password("strong-password")
    student = User(full_name="طالبة الاختبار", email="student-test@example.com", role="student")
    student.set_password("strong-password")
    db.session.add_all([teacher, student])
    db.session.flush()

    curriculum = Curriculum(created_by_id=teacher.id, name="منهج تجريبي", subject="تاريخ", grade="11", semester="1", academic_year="2026", version="test")
    db.session.add(curriculum)
    db.session.flush()
    unit = Unit(curriculum_id=curriculum.id, title="وحدة", order_index=1)
    db.session.add(unit)
    db.session.flush()
    lesson = Lesson(unit_id=unit.id, title="درس", slug="lifecycle-test", order_index=1, is_published=True)
    db.session.add(lesson)
    db.session.flush()
    worksheet = Worksheet(lesson_id=lesson.id, created_by_id=teacher.id, title="ورقة مؤقتة", publication_status="published", is_published=True, time_limit_minutes=10)
    db.session.add(worksheet)
    db.session.commit()
    teacher_id, student_id, worksheet_id = teacher.id, student.id, worksheet.id

client = app.test_client()
with client.session_transaction() as session:
    session["_user_id"] = str(teacher_id)
    session["_fresh"] = True

response = client.post(f"/teacher-dashboard/worksheets/{worksheet_id}/archive")
assert response.status_code == 302

with app.app_context():
    worksheet = db.session.get(Worksheet, worksheet_id)
    assert worksheet.is_archived is True
    assert worksheet.is_published is False

response = client.post(f"/teacher-dashboard/worksheets/{worksheet_id}/restore")
assert response.status_code == 302

with app.app_context():
    worksheet = db.session.get(Worksheet, worksheet_id)
    worksheet.publication_status = "published"
    worksheet.is_published = True
    attempt = WorksheetAttempt(
        worksheet_id=worksheet.id,
        student_id=student_id,
        started_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=11),
    )
    db.session.add(attempt)
    db.session.commit()
    assert get_remaining_seconds(attempt) == 0

response = client.post(f"/teacher-dashboard/worksheets/{worksheet_id}/delete")
assert response.status_code == 302
with app.app_context():
    assert db.session.get(Worksheet, worksheet_id) is not None

print("PASS: worksheet archive, protected deletion, and server-side timer")
