"""Small integration test for worksheet visibility, archiving and timing."""

import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


database_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
database_file.close()
os.environ["DATABASE_URL"] = f"sqlite:///{database_file.name}"

from app import app  # noqa: E402
from alrayyan.extensions import db  # noqa: E402
from alrayyan.models import ClassEnrollment, Classroom, Curriculum, Lesson, Question, Unit, User, Worksheet, WorksheetAttempt, WorksheetAttachment  # noqa: E402
from alrayyan.routes.assessment import get_remaining_seconds  # noqa: E402


app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
upload_directory = tempfile.mkdtemp(prefix="alrayyan-uploads-")
app.config["UPLOAD_FOLDER"] = upload_directory

with app.app_context():
    db.create_all()
    teacher = User(full_name="معلمة الاختبار", email="teacher-test@example.com", role="teacher")
    teacher.set_password("strong-password")
    student = User(full_name="طالبة الاختبار", email="student-test@example.com", role="student")
    student.set_password("strong-password")
    db.session.add_all([teacher, student])
    db.session.flush()

    # Grade access now fails closed for unassigned students; give this test
    # student a real grade-11 enrollment so the download checks are meaningful.
    classroom = Classroom(
        teacher_id=teacher.id,
        name="صف الاختبار",
        grade="11",
        academic_year="2026",
        is_active=True,
    )
    db.session.add(classroom)
    db.session.flush()
    db.session.add(ClassEnrollment(classroom_id=classroom.id, student_id=student.id))

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
    question = Question(
        worksheet_id=worksheet.id,
        question_text="سؤال محفوظ",
        question_type="short_answer",
        correct_answer_text="إجابة",
        points=2,
        order_index=1,
    )
    db.session.add(question)
    db.session.flush()
    question_id = question.id
    attempt = WorksheetAttempt(
        worksheet_id=worksheet.id,
        student_id=student_id,
        started_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=11),
    )
    db.session.add(attempt)
    db.session.commit()
    assert get_remaining_seconds(attempt) == 0

response = client.post(f"/assessment/teacher/questions/{question_id}/delete")
assert response.status_code == 302
with app.app_context():
    assert db.session.get(Question, question_id) is not None

# Verify that uploaded files download for both worksheets and tests.
with app.app_context():
    upload_path = Path(upload_directory) / "worksheet-test.pdf"
    upload_path.write_bytes(b"%PDF-1.4 test file")
    attachment = WorksheetAttachment(
        worksheet_id=worksheet_id,
        attachment_type="worksheet",
        original_filename="ملف اختبار.pdf",
        stored_filename="worksheet-test.pdf",
        storage_path="worksheet-test.pdf",
        file_extension=".pdf",
        mime_type="application/pdf",
        file_size=upload_path.stat().st_size,
    )
    db.session.add(attachment)
    db.session.commit()

with client.session_transaction() as session:
    session["_user_id"] = str(student_id)
    session["_fresh"] = True

response = client.get(f"/worksheets/{worksheet_id}/download")
assert response.status_code == 200, response.status_code
assert response.data == b"%PDF-1.4 test file"
assert "attachment" in response.headers.get("Content-Disposition", "").lower()

with app.app_context():
    worksheet = db.session.get(Worksheet, worksheet_id)
    worksheet.creation_method = "test"
    upload_path = Path(upload_directory) / "worksheet-test-extra.pdf"
    upload_path.write_bytes(b"%PDF-1.4 test file")
    db.session.add(WorksheetAttachment(
        worksheet_id=worksheet_id,
        attachment_type="worksheet",
        original_filename="test.pdf",
        stored_filename="worksheet-test-extra.pdf",
        storage_path="worksheet-test-extra.pdf",
        file_extension=".pdf",
        mime_type="application/pdf",
        file_size=upload_path.stat().st_size,
    ))
    db.session.commit()

response = client.get(f"/worksheets/{worksheet_id}")
assert response.status_code == 200, response.status_code

response = client.get(f"/worksheets/{worksheet_id}/download")
assert response.status_code == 200, response.status_code
assert response.data == b"%PDF-1.4 test file"

with client.session_transaction() as session:
    session["_user_id"] = str(teacher_id)
    session["_fresh"] = True

response = client.post(f"/teacher-dashboard/worksheets/{worksheet_id}/delete")
assert response.status_code == 302
with app.app_context():
    assert db.session.get(Worksheet, worksheet_id) is not None

print("PASS: worksheet archive, protected deletion, and server-side timer")
