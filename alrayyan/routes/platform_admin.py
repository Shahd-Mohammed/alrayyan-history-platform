import csv
import json
import os
import re
import smtplib
import ssl
import urllib.error
import urllib.request
from email.message import EmailMessage
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from io import BytesIO, StringIO

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from sqlalchemy import func
from alrayyan.services.grade_access import (selected_management_grade, normalize_grade, lesson_ids_for_grade, curriculum_ids_for_grade, classroom_ids_for_grade, student_ids_for_grade)
from flask_login import current_user, login_required

from alrayyan.extensions import db
from alrayyan.forms import ClassroomForm, ConceptMapForm, ConceptMapUploadForm, CurriculumUploadForm, HistoricalCharacterForm, InvitationForm, LearningResourceForm, PlatformSettingsForm
from alrayyan.services.file_storage import upload_to_object_storage
from alrayyan.models import CharacterAttempt, ClassEnrollment, Classroom, ConceptMap, DateReview, HistoricalDate, ConceptMapEdge, ConceptMapNode, ConceptMastery, ContentChunk, Curriculum, HistoricalCharacter, HonorBoardEntry, LearningResource, Lesson, PlatformSettings, SourceDocument, StudentInvitation, TutorConversation, TutorMessage, LearningPlanItem, Unit, User, Worksheet, WorksheetAttempt, ChallengeSession, XPTransaction
from alrayyan.services.document_reader import calculate_checksum, extract_docx, extract_pdf
from alrayyan.services.text_processing import chunk_text, create_text_hash
from alrayyan.services.curriculum_processing import process_source_document
from alrayyan.services.learning_content_ai import (
    generate_character_drafts,
    generate_concept_map_draft,
)
from alrayyan.services.embeddings import generate_embeddings, get_embedding_settings

platform_admin_bp = Blueprint("platform_admin", __name__, url_prefix="/teacher-dashboard/platform")


def _safe_admin_return_url(default_endpoint):
    """Accept a same-site relative return path for post/redirect/get flows."""
    target = (request.form.get("return_to") or request.args.get("return_to") or "").strip()
    if target.startswith("/") and not target.startswith("//") and chr(92) not in target:
        return target
    return url_for(default_endpoint)


@platform_admin_bp.before_request
@login_required
def teacher_only():
    if current_user.role not in {"teacher", "admin"}:
        abort(403)
    selected_management_grade()


def teacher_curricula():
    query = Curriculum.query
    if current_user.role != "admin":
        query = query.filter((Curriculum.created_by_id == current_user.id) | (Curriculum.created_by_id.is_(None)))
    query = query.filter(Curriculum.id.in_(curriculum_ids_for_grade(selected_management_grade()) or [-1]))
    return query


def teacher_lessons():
    # Lesson selectors include every curriculum that the teacher has
    # explicitly activated. Activation is independent per curriculum.
    # Inactive curricula must never leak into teacher-facing dropdowns.
    # Ignore legacy placeholder lessons left by older curriculum parsing.
    placeholder_titles = {
        "محتوى المنهج",
        "الدرس احتياطي",
        "الوحدة — الدرس احتياطي",
    }
    query = Lesson.query.join(Unit).join(Curriculum).filter(
        Curriculum.is_active.is_(True),
        Curriculum.processing_status == "ready",
        Lesson.title.notin_(placeholder_titles),
    )

    # Admins manage shared platform curricula, including curricula uploaded
    # by another teacher. Non-admin teachers only see their own or shared
    # (ownerless) curricula, matching teacher_curricula().
    query = query.filter(Lesson.id.in_(lesson_ids_for_grade(selected_management_grade()) or [-1]))
    if current_user.role != "admin":
        query = query.filter(
            (Curriculum.created_by_id == current_user.id)
            | (Curriculum.created_by_id.is_(None))
        )

    return query.order_by(
        Curriculum.subject,
        Curriculum.grade,
        Unit.order_index,
        Lesson.order_index,
    ).all()


def lesson_choices():
    return [(lesson.id, f"{lesson.unit.title} — {lesson.title}") for lesson in teacher_lessons()]


def curriculum_ready_for_activation(curriculum):
    if curriculum.processing_status != "ready" or not curriculum.sources:
        return False
    chunks = ContentChunk.query.join(SourceDocument).filter(
        SourceDocument.curriculum_id == curriculum.id,
    ).all()
    return bool(chunks) and all(
        chunk.embedding and chunk.embedding_model and chunk.embedding_dimensions
        for chunk in chunks
    )


def normalize_active_curricula():
    """Compatibility hook: active curricula are controlled manually."""
    return {
        (curriculum.subject, curriculum.grade): curriculum
        for curriculum in Curriculum.query.filter_by(is_active=True).all()
    }


def activate_curriculum(curriculum):
    if not curriculum_ready_for_activation(curriculum):
        raise ValueError("المنهج لم يكتمل تجهيزه وفهرسته: يجب أن تكون كل المقاطع مستخرجة ومفهرسة بالـembeddings قبل التفعيل.")

    # Activation is an independent manual choice. Enabling one curriculum
    # must never deactivate another curriculum.
    curriculum.is_active = True
    curriculum.processing_status = "ready"
    curriculum.activated_at = datetime.now(timezone.utc).replace(tzinfo=None)

    for source in curriculum.sources:
        source.is_active = True


def owned_lesson_or_404(lesson_id):
    lesson = db.session.get(Lesson, lesson_id)
    if lesson is None or lesson.id not in {item.id for item in teacher_lessons()}:
        abort(404)
    return lesson


def save_upload(upload, folder_name, allowed, persist=True):
    original = (upload.filename or "").strip()
    extension = Path(original).suffix.lower()
    if extension.lstrip(".") not in allowed:
        raise ValueError("صيغة الملف غير مسموحة")
    folder = Path(current_app.config["UPLOAD_FOLDER"]) / folder_name
    folder.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid4().hex}{extension}"
    path = folder / stored_name
    upload.save(path)
    relative = str(Path(folder_name) / stored_name).replace("\\", "/")
    if persist:
        try:
            upload_to_object_storage(path, relative)
        except Exception:
            path.unlink(missing_ok=True)
            raise
    return original, path, relative




def platform_owner_emails():
    """Return the two explicitly trusted platform-owner email addresses."""
    configured = os.getenv(
        "PLATFORM_OWNER_EMAILS",
        "1shahdmohammed@gmail.com,miss.emmy2020@gmail.com",
    )
    return {
        email.strip().casefold()
        for email in configured.split(",")
        if email.strip()
    }


def is_platform_owner_account(user):
    """Identify a configured owner account for display-only navigation rules."""
    return bool(
        user
        and user.is_authenticated
        and (user.email or "").strip().casefold() in platform_owner_emails()
    )


def is_platform_owner(user):
    """Grant owner permissions only to a configured account with the admin role."""
    return bool(
        is_platform_owner_account(user)
        and user.role == "admin"
    )


@platform_admin_bp.app_context_processor
def inject_platform_owner_permission():
    return {
        "is_platform_owner": is_platform_owner,
        "is_platform_owner_account": is_platform_owner_account,
        "selected_grade": selected_management_grade(),
    }

@platform_admin_bp.route("/curricula", methods=["GET", "POST"])
def curricula():
    form = CurriculumUploadForm()
    if form.validate_on_submit():
        if normalize_grade(form.grade.data) != selected_management_grade():
            flash("اختاري تبويب الصف المطابق للمنهج الذي تريدين رفعه.", "error")
            return redirect(url_for("platform_admin.curricula"))
        stored_path = None
        try:
            stored_path = None
            original, stored_path, relative = save_upload(
                form.document.data, "curricula", {"pdf", "docx"}, persist=False
            )
            curriculum_query = teacher_curricula().filter_by(
                subject=form.subject.data.strip(),
                grade=form.grade.data.strip(),
                semester=form.semester.data,
                academic_year=form.academic_year.data.strip(),
            ).order_by(Curriculum.created_at.desc())
            curriculum = curriculum_query.first()
            if curriculum is None or curriculum.is_active:
                versions = [str(item.version) for item in curriculum_query.all()]
                version_numbers = []
                for version in versions:
                    try:
                        version_numbers.append(float(version))
                    except (TypeError, ValueError):
                        continue
                next_version = f"{(max(version_numbers) + 1.0) if version_numbers else 1.0:.1f}"
                curriculum = Curriculum(
                    created_by_id=current_user.id,
                    name=(form.curriculum_name.data or "").strip() or f"{form.subject.data.strip()} — {form.grade.data.strip()} — الفصل {form.semester.data} — {form.academic_year.data.strip()}",
                    subject=form.subject.data.strip(),
                    grade=form.grade.data.strip(),
                    semester=form.semester.data,
                    academic_year=form.academic_year.data.strip(),
                    version=next_version,
                    is_active=False,
                    processing_status="processing",
                )
                db.session.add(curriculum)
                db.session.flush()
            else:
                curriculum.processing_status = "processing"
                curriculum.processing_error = None
                curriculum.is_active = False
                for source in curriculum.sources:
                    source.is_active = False

            checksum = calculate_checksum(stored_path)
            if SourceDocument.query.filter_by(curriculum_id=curriculum.id, checksum=checksum).first():
                raise ValueError("هذا الملف موجود مسبقًا داخل المنهج نفسه")

            extracted = (
                extract_pdf(stored_path)
                if stored_path.suffix.lower() == ".pdf"
                else extract_docx(stored_path)
            )

            source_priority = {
                "official_book": 1,
                "supporting_book": 2,
                "review_notes": 3,
            }[form.source_type.data]

            source = SourceDocument(
                curriculum_id=curriculum.id,
                lesson_id=None,
                title=(form.source_title.data or "").strip() or Path(original).stem,
                source_type=form.source_type.data,
                original_filename=original,
                stored_path=relative,
                page_count=extracted.get("page_count"),
                checksum=checksum,
                academic_year=curriculum.academic_year,
                priority=source_priority,
                is_primary=form.source_type.data == "official_book",
                is_active=True,
            )
            db.session.add(source)
            db.session.flush()

            extracted_count = process_source_document(
                source,
                fallback_unit_title=(form.unit_title.data or "").strip(),
                fallback_lesson_title=(form.lesson_title.data or "").strip(),
            )
            # Uploading and indexing a curriculum does not activate it.
            # Activation remains an explicit manual choice from the curriculum
            # management screen.
            curriculum.is_active = False
            for item in curriculum.sources:
                item.is_active = False
            curriculum.processing_status = "ready"
            # The original curriculum is persisted only after successful extraction/indexing.
            upload_to_object_storage(stored_path, relative)
            db.session.commit()
            flash(
                f"تم تحليل وفهرسة {extracted_count} مقطعًا. المنهج جاهز ويمكنك تفعيله يدويًا من قائمة المناهج.",
                "success",
            )
            return redirect(url_for("platform_admin.curricula"))
        except Exception as error:
            db.session.rollback()
            if stored_path and stored_path.exists():
                stored_path.unlink()
            current_app.logger.exception("Curriculum upload failed")
            flash(f"تعذر تجهيز المصدر: {error}", "error")

    normalize_active_curricula()

    return render_template(
        "platform/curricula.html",
        form=form,
        curricula=teacher_curricula().order_by(Curriculum.created_at.desc()).all(),
    )


@platform_admin_bp.post("/curricula/<int:curriculum_id>/reindex")
def reindex_curriculum(curriculum_id):
    curriculum = teacher_curricula().filter_by(id=curriculum_id).first_or_404()
    if not curriculum.sources:
        flash("لا يوجد ملف مصدر لإعادة تجهيزه داخل هذا المنهج.", "error")
        return redirect(url_for("platform_admin.curricula"))

    try:
        curriculum.processing_status = "processing"
        curriculum.processing_error = None
        total_chunks = 0
        for source in curriculum.sources:
            total_chunks += process_source_document(source)

        curriculum.processing_status = "ready"
        db.session.commit()
        flash(
            f"تمت إعادة تجهيز وفهرسة {total_chunks} مقطعًا. يمكنك الآن تفعيل المنهج.",
            "success",
        )
    except Exception as error:
        db.session.rollback()
        current_app.logger.exception("Curriculum reindex failed")
        flash(f"تعذر إعادة تجهيز المنهج: {error}", "error")

    return redirect(url_for("platform_admin.curricula"))


@platform_admin_bp.post("/curricula/<int:curriculum_id>/delete")
def delete_curriculum(curriculum_id):
    curriculum = teacher_curricula().filter_by(id=curriculum_id).first_or_404()

    # Allow removal of unused assessment content, but never cascade-delete curriculum
    # lessons that have student attempts or recorded learning history. Archive
    # or deactivate the curriculum when historical activity is linked to it.
    lesson_ids = [
        lesson.id
        for unit in curriculum.units
        for lesson in unit.lessons
    ]
    if lesson_ids:
        worksheet_ids = db.session.query(Worksheet.id).filter(
            Worksheet.lesson_id.in_(lesson_ids)
        )
        has_worksheet_attempts = WorksheetAttempt.query.filter(
            WorksheetAttempt.worksheet_id.in_(worksheet_ids)
        ).first() is not None
        has_mastery_records = ConceptMastery.query.filter(
            ConceptMastery.lesson_id.in_(lesson_ids)
        ).first() is not None
        has_challenge_sessions = ChallengeSession.query.filter(
            ChallengeSession.lesson_id.in_(lesson_ids)
        ).first() is not None
        has_date_reviews = DateReview.query.join(HistoricalDate).filter(
            HistoricalDate.lesson_id.in_(lesson_ids)
        ).first() is not None
        has_tutor_conversations = TutorConversation.query.filter(
            TutorConversation.lesson_id.in_(lesson_ids)
        ).first() is not None
        has_learning_plan_items = LearningPlanItem.query.filter(
            LearningPlanItem.lesson_id.in_(lesson_ids)
        ).first() is not None
        character_ids = db.session.query(HistoricalCharacter.id).filter(
            HistoricalCharacter.lesson_id.in_(lesson_ids)
        )
        has_character_attempts = CharacterAttempt.query.filter(
            CharacterAttempt.character_id.in_(character_ids)
        ).first() is not None
        concept_map_ids = db.session.query(ConceptMap.id).filter(
            ConceptMap.lesson_id.in_(lesson_ids)
        )
        has_concept_map_rewards = XPTransaction.query.filter(
            XPTransaction.reason == "concept_map_viewed",
            XPTransaction.source_id.in_(concept_map_ids),
        ).first() is not None

        # Deleting lessons cascades to worksheets, characters, maps and dates;
        # protect every linked student record before SQLAlchemy can cascade.
        if (
            has_worksheet_attempts
            or has_mastery_records
            or has_challenge_sessions
            or has_date_reviews
            or has_tutor_conversations
            or has_learning_plan_items
            or has_character_attempts
            or has_concept_map_rewards
        ):
            flash(
                "لا يمكن حذف هذا المنهج لأنه مرتبط بمحاولات أو سجلات تعلم للطالبات. "
                "عطّلي المنهج، أو احتفظي بنسخة أرشيفية منه قبل بدء فصل جديد.",
                "error",
            )
            return redirect(url_for("platform_admin.curricula"))

    relative_paths = [source.stored_path for source in curriculum.sources if source.stored_path]
    was_active = curriculum.is_active

    try:
        db.session.delete(curriculum)
        db.session.commit()
    except Exception as error:
        db.session.rollback()
        current_app.logger.exception("Curriculum deletion failed")
        flash(f"تعذر حذف المنهج: {error}", "error")
        return redirect(url_for("platform_admin.curricula"))

    upload_root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    for relative_path in relative_paths:
        target = (upload_root / relative_path).resolve()
        if target.is_relative_to(upload_root) and target.is_file():
            try:
                target.unlink()
            except OSError:
                current_app.logger.warning("Could not remove curriculum file: %s", target)

    flash(
        "تم حذف المنهج ومصادره وملفاته نهائيًا."
        if was_active
        else "تم حذف المنهج ومصادره وملفاته نهائيًا.",
        "success",
    )
    return redirect(url_for("platform_admin.curricula"))


@platform_admin_bp.post("/curricula/<int:curriculum_id>/toggle")
def toggle_curriculum(curriculum_id):
    curriculum = teacher_curricula().filter_by(id=curriculum_id).first_or_404()
    new_state = not curriculum.is_active
    if new_state:
        try:
            activate_curriculum(curriculum)
            db.session.commit()
        except Exception as error:
            db.session.rollback()
            flash(str(error), "error")
            return redirect(url_for("platform_admin.curricula"))
    else:
        curriculum.is_active = False
        for source in curriculum.sources:
            source.is_active = False

        # Deactivation is also independent. Do not automatically
        # activate another curriculum when this one is switched off.
        db.session.commit()
    flash("تم تحديث حالة المنهج ومصادره", "success")
    return redirect(url_for("platform_admin.curricula"))


@platform_admin_bp.route("/classrooms", methods=["GET", "POST"])
def classrooms():
    form = ClassroomForm()
    if form.validate_on_submit():
        if normalize_grade(form.grade.data) != selected_management_grade():
            flash("اختاري تبويب الصف المطابق للفصل الذي تريدين إنشاءه.", "error")
            return redirect(url_for("platform_admin.classrooms"))
        db.session.add(Classroom(teacher_id=current_user.id, name=form.name.data.strip(), grade=form.grade.data.strip(), academic_year=form.academic_year.data.strip(), whatsapp_url=(form.whatsapp_url.data or "").strip() or None))
        db.session.commit(); flash("تم إنشاء الصف", "success")
        return redirect(url_for("platform_admin.classrooms"))
    query = Classroom.query if current_user.role == "admin" else Classroom.query.filter_by(teacher_id=current_user.id)
    query = query.filter(Classroom.id.in_(classroom_ids_for_grade(selected_management_grade(), teacher_id=None if current_user.role == "admin" else current_user.id, active_only=False) or [-1]))
    return render_template("platform/classrooms.html", form=form, classrooms=query.order_by(Classroom.created_at.desc()).all())


@platform_admin_bp.post("/classrooms/<int:classroom_id>/delete")
def delete_classroom(classroom_id):
    classroom = Classroom.query.filter_by(id=classroom_id, teacher_id=current_user.id).first_or_404()
    if classroom.id not in set(classroom_ids_for_grade(selected_management_grade(), teacher_id=current_user.id, active_only=False)):
        abort(404)
    try:
        # Removing a class only removes enrollments; student accounts and worksheet results stay intact.
        db.session.delete(classroom)
        db.session.commit()
        flash("تم حذف الصف وإزالة ارتباط الطالبات به، مع الحفاظ على حساباتهن ونتائجهن.", "success")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Classroom deletion failed")
        flash("تعذر حذف الصف. لم يتم تغيير البيانات.", "error")
    return redirect(url_for("platform_admin.classrooms"))


def invitation_mail_settings():
    # Resend uses HTTPS and works with Render Free services; outbound SMTP
    # ports (25/465/587) are blocked on Render's free web-service tier.
    if os.getenv("RESEND_API_KEY") and os.getenv("RESEND_FROM_EMAIL"):
        return True
    return all(
        os.getenv(key)
        for key in ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM_EMAIL")
    )


def send_student_invitation(email, invitation_url, teacher_name):
    sender = os.getenv("RESEND_FROM_EMAIL") or os.getenv("SMTP_FROM_EMAIL")
    subject = "دعوة للانضمام إلى منصة الريان للدراسات التاريخية"
    body = (
        f"مرحبًا،\n\nدعتك المعلمة {teacher_name} للانضمام إلى منصة الريان للدراسات التاريخية.\n"
        f"افتحي الرابط التالي لإنشاء حسابك: {invitation_url}\n\n"
        "إذا لم تتوقعي هذه الدعوة، يمكنك تجاهل هذه الرسالة."
    )

    resend_api_key = (os.getenv("RESEND_API_KEY") or "").strip()
    if resend_api_key and sender:
        payload = json.dumps({
            "from": sender,
            "to": [email],
            "subject": subject,
            "text": body,
        }).encode("utf-8")
        api_request = urllib.request.Request(
            "https://api.resend.com/emails",
            data=payload,
            headers={
                "Authorization": f"Bearer {resend_api_key}",
                "Content-Type": "application/json",
                "User-Agent": "Alrayyan-History-Platform/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(api_request, timeout=25) as response:
                if response.status < 200 or response.status >= 300:
                    raise RuntimeError(f"خدمة البريد رفضت الطلب (HTTP {response.status})")
                return json.loads(response.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(
                f"فشل إرسال الدعوة عبر خدمة البريد (HTTP {error.code}): {details}"
            ) from error
        except urllib.error.URLError as error:
            raise RuntimeError(
                "تعذر الاتصال بخدمة البريد عبر HTTPS. تحققي من سجل Render."
            ) from error

    host, username, password = (
        os.getenv(key)
        for key in ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD")
    )
    if not all((host, username, password, sender)):
        raise RuntimeError(
            "إعدادات البريد غير مكتملة. أضيفي RESEND_API_KEY وRESEND_FROM_EMAIL "
            "في Render أو أكملي إعداد SMTP."
        )

    port = int(os.getenv("SMTP_PORT", "587"))
    ssl_setting = os.getenv("SMTP_USE_SSL")
    use_ssl = (
        ssl_setting.lower() in {"1", "true", "yes"}
        if ssl_setting is not None
        else port == 465
    )
    use_tls = os.getenv("SMTP_USE_TLS", "1").lower() not in {"0", "false", "no"}

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = email
    message["Reply-To"] = sender
    message.set_content(body)

    smtp_client = (
        smtplib.SMTP_SSL(
            host, port, timeout=20, context=ssl.create_default_context()
        )
        if use_ssl
        else smtplib.SMTP(host, port, timeout=20)
    )
    with smtp_client as server:
        if not use_ssl and use_tls:
            server.starttls(context=ssl.create_default_context())
        server.login(username, password)
        refused = server.send_message(message)
        if refused:
            raise smtplib.SMTPRecipientsRefused(refused)


def extract_invitation_emails(upload):
    extension = Path(upload.filename or "").suffix.lower()
    if extension not in {".xlsx", ".csv"}:
        raise ValueError("ارفعي ملف Excel بصيغة ‎.xlsx أو ملف ‎.csv.")
    raw = upload.read()
    values = []
    if extension == ".csv":
        try:
            content = raw.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise ValueError("تعذر قراءة ملف CSV؛ احفظيه بترميز UTF-8.") from error
        for row in csv.reader(StringIO(content)):
            values.extend(str(cell).strip() for cell in row if cell is not None)
    else:
        try:
            from openpyxl import load_workbook
            workbook = load_workbook(BytesIO(raw), read_only=True, data_only=True)
            for sheet in workbook.worksheets:
                for row in sheet.iter_rows(values_only=True):
                    values.extend(str(cell).strip() for cell in row if cell is not None)
            workbook.close()
        except Exception as error:
            raise ValueError("تعذر قراءة ملف Excel. تأكدي أنه ملف ‎.xlsx سليم.") from error
    pattern = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
    emails = []
    malformed = []
    for value in values:
        candidates = re.split(r"[\s,;]+", value.lower())
        for candidate in candidates:
            candidate = candidate.strip().strip("()<>[]{}.,")
            if not candidate:
                continue
            if "@" in candidate:
                if pattern.fullmatch(candidate):
                    if candidate not in emails:
                        emails.append(candidate)
                else:
                    malformed.append(candidate)
    if malformed:
        raise ValueError("يوجد عنوان بريد غير صالح في الملف: " + "، ".join(malformed[:5]))
    if not emails:
        raise ValueError("لم أجد عناوين بريد إلكتروني صالحة داخل الملف.")
    return emails


@platform_admin_bp.route("/invitations", methods=["GET", "POST"])
def invitations():
    form = InvitationForm()
    classes = Classroom.query.filter(Classroom.id.in_(classroom_ids_for_grade(selected_management_grade(), teacher_id=current_user.id, active_only=True) or [-1])).all()
    form.classroom_id.choices = [(0, "اختاري الصف")] + [(row.id, row.name) for row in classes]
    invitation_urls = []
    upload = request.files.get("emails_file")
    is_file_upload = request.method == "POST" and upload is not None and bool(upload.filename)
    if request.method == "POST" and not classes:
        flash("لا توجد صفوف نشطة لإرسال الدعوات إليها. أنشئي الصف أولًا ثم أعيدي المحاولة.", "error")
    elif is_file_upload:
        try:
            emails = extract_invitation_emails(upload)
            classroom_id = request.form.get("classroom_id", type=int)
            if not classroom_id:
                raise ValueError("اختاري الصف الذي ستنضم إليه الطالبات قبل إنشاء الدعوات.")
            if not any(row.id == classroom_id for row in classes):
                abort(403)
            valid_days = request.form.get("valid_days", default=7, type=int)
            if not 1 <= valid_days <= 30:
                raise ValueError("مدة صلاحية الدعوة يجب أن تكون بين يوم و30 يومًا.")
            invitation_urls = create_invitation_batch(emails, classroom_id, valid_days)
        except ValueError as error:
            flash(str(error), "error")
        except Exception as error:
            db.session.rollback()
            current_app.logger.exception("Bulk invitation upload failed")
            flash(f"تعذر معالجة الملف: {error}", "error")
    elif form.validate_on_submit():
        classroom_id = form.classroom_id.data
        if not classroom_id or not any(row.id == classroom_id for row in classes):
            flash("اختاري صفًا نشطًا وصحيحًا قبل إنشاء الدعوات.", "error")
        else:
            emails = []
            for email in re.split(r"[\s,;]+", form.emails.data or ""):
                normalized = email.strip().lower()
                if normalized and normalized not in emails:
                    emails.append(normalized)
            invalid = [email for email in emails if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)]
            if invalid:
                form.emails.errors.append("بعض العناوين غير صالحة: " + "، ".join(invalid[:5]))
            else:
                invitation_urls = create_invitation_batch(emails, classroom_id, form.valid_days.data)
    query = StudentInvitation.query if current_user.role == "admin" else StudentInvitation.query.filter_by(teacher_id=current_user.id)
    selected_classroom_ids = classroom_ids_for_grade(selected_management_grade(), teacher_id=None if current_user.role == "admin" else current_user.id, active_only=False)
    query = query.filter(StudentInvitation.classroom_id.in_(selected_classroom_ids or [-1]))

    # Accepted invitations whose students no longer have an active membership
    # in this grade can reveal accounts left behind after a classroom was removed.
    selected_grade = selected_management_grade()
    accepted_invitations = StudentInvitation.query.filter(
        StudentInvitation.teacher_id == current_user.id,
        StudentInvitation.accepted_at.isnot(None),
    ).all()
    # Only show missing links for this grade. An invitation still attached to a
    # different-grade classroom is not an orphan in the current workspace.
    accepted_emails = list({
        (row.email or "").strip().lower()
        for row in accepted_invitations
        if row.classroom_id is None
        or row.classroom is None
        or normalize_grade(row.classroom.grade) == selected_grade
    })
    enrolled_student_ids = set(student_ids_for_grade(
        selected_grade,
        teacher_id=None if current_user.role == "admin" else current_user.id,
        active_only=True,
    ))
    candidates = User.query.filter(
        User.role == "student",
        User.is_active_account.is_(True),
        func.lower(User.email).in_(accepted_emails or [""]),
    ).order_by(User.full_name.asc()).all() if accepted_emails else []
    orphaned_students = [
        student for student in candidates if student.id not in enrolled_student_ids
    ]

    current_grade_student_ids = student_ids_for_grade(
        selected_grade,
        teacher_id=None if current_user.role == "admin" else current_user.id,
        active_only=True,
    )
    grade_students = User.query.filter(
        User.id.in_(current_grade_student_ids or [-1]),
        User.role == "student",
        User.is_active_account.is_(True),
    ).order_by(User.full_name.asc()).all()

    return render_template(
        "platform/invitations.html",
        form=form,
        invitations=query.order_by(StudentInvitation.created_at.desc()).limit(200).all(),
        invitation_urls=invitation_urls,
        classrooms=classes,
        orphaned_students=orphaned_students,
        grade_students=grade_students,
        selected_grade=selected_grade,
    )


@platform_admin_bp.post("/students/<int:student_id>/remove-from-grade")
def remove_student_from_grade(student_id):
    """Remove a student only from the currently selected grade, preserving history."""
    selected_grade = selected_management_grade()
    allowed_classroom_ids = classroom_ids_for_grade(
        selected_grade,
        teacher_id=None if current_user.role == "admin" else current_user.id,
        active_only=False,
    )
    if not allowed_classroom_ids:
        abort(404)

    student = User.query.filter_by(
        id=student_id,
        role="student",
        is_active_account=True,
    ).first_or_404()
    memberships = ClassEnrollment.query.filter(
        ClassEnrollment.student_id == student.id,
        ClassEnrollment.classroom_id.in_(allowed_classroom_ids),
    ).all()
    if not memberships:
        abort(404)

    for membership in memberships:
        db.session.delete(membership)
    db.session.commit()
    flash(
        f"تمت إزالة {student.first_name} من صف {selected_grade} فقط. بقي حسابها ونتائجها ونقاطها محفوظة، ولم يتغير أي ارتباط بصف آخر.",
        "success",
    )
    return redirect(url_for("platform_admin.invitations"))


@platform_admin_bp.post("/invitations/relink/<int:student_id>")
def relink_existing_student(student_id):
    """Restore a previously invited student to an active classroom without recreating the account."""
    classroom_id = request.form.get("classroom_id", type=int)
    classroom_query = Classroom.query.filter_by(id=classroom_id, is_active=True)
    if current_user.role != "admin":
        classroom_query = classroom_query.filter_by(teacher_id=current_user.id)
    classroom = classroom_query.first_or_404()
    if normalize_grade(classroom.grade) != selected_management_grade():
        abort(403)

    student = User.query.filter_by(
        id=student_id,
        role="student",
        is_active_account=True,
    ).first_or_404()
    prior_invitation = StudentInvitation.query.filter(
        StudentInvitation.teacher_id == current_user.id,
        func.lower(StudentInvitation.email) == (student.email or "").strip().lower(),
        StudentInvitation.accepted_at.isnot(None),
    ).first()
    if prior_invitation is None:
        abort(403)

    enrollment = ClassEnrollment.query.filter_by(
        classroom_id=classroom.id,
        student_id=student.id,
    ).first()
    if enrollment is None:
        db.session.add(ClassEnrollment(
            classroom_id=classroom.id,
            student_id=student.id,
        ))
        db.session.commit()
        flash(
            f"رجعنا ربط حساب {student.first_name} بالصف المختار، واحتفظنا بتقدّمها ونتائجها.",
            "success",
        )
    else:
        flash("الطالبة مرتبطة بهذا الصف بالفعل؛ لم تتغير بياناتها.", "info")
    return redirect(url_for("platform_admin.invitations"))


def create_invitation_batch(emails, classroom_id, valid_days):
    normalized_emails = list(dict.fromkeys(
        (email or "").strip().lower() for email in emails if (email or "").strip()
    ))
    classroom_query = Classroom.query.filter_by(id=classroom_id, is_active=True)
    if current_user.role != "admin":
        classroom_query = classroom_query.filter_by(teacher_id=current_user.id)
    classroom = classroom_query.first()
    if classroom is None or normalize_grade(classroom.grade) != selected_management_grade():
        raise ValueError("اختاري صفًا نشطًا تابعًا لمساحة الصف الحالية.")

    existing_users = {
        (row.email or "").strip().lower(): row
        for row in User.query.filter(func.lower(User.email).in_(normalized_emails)).all()
    } if normalized_emails else {}
    pending = StudentInvitation.query.filter(
        StudentInvitation.teacher_id == current_user.id,
        func.lower(StudentInvitation.email).in_(normalized_emails),
        StudentInvitation.accepted_at.is_(None),
        StudentInvitation.expires_at > datetime.utcnow(),
    ).all() if normalized_emails else []
    pending_by_email = {}
    for row in pending:
        pending_by_email.setdefault(row.email.strip().lower(), []).append(row)

    invitation_urls = []
    renewed_count = 0
    linked_count = 0
    already_linked_count = 0
    for email in normalized_emails:
        existing_user = existing_users.get(email)
        if existing_user is not None:
            # An existing student account can be re-linked to the class when
            # the teacher explicitly submits that email and chooses this class.
            # Never create duplicate memberships or modify the account/results.
            if existing_user.role == "student" and existing_user.is_active_account:
                enrollment = ClassEnrollment.query.filter_by(
                    classroom_id=classroom.id,
                    student_id=existing_user.id,
                ).first()
                if enrollment is None:
                    db.session.add(ClassEnrollment(
                        classroom_id=classroom.id,
                        student_id=existing_user.id,
                    ))
                    linked_count += 1
                else:
                    already_linked_count += 1
            continue

        # A valid invitation previously created for this address has a token
        # hash only, so its original link cannot be recovered. Expire that
        # link and issue a fresh token instead of silently skipping the email.
        old_invitations = pending_by_email.get(email, [])
        if old_invitations:
            for old_invitation in old_invitations:
                old_invitation.expires_at = datetime.utcnow()
            renewed_count += 1

        invitation, token = StudentInvitation.create(
            current_user.id, email, classroom.id, valid_days
        )
        db.session.add(invitation)
        invitation_urls.append({
            "email": email,
            "url": url_for(
                "auth.register_invitation",
                token=token,
                _external=True,
            ),
        })

    db.session.commit()
    if linked_count:
        flash(
            f"تم ربط {linked_count} طالبة مسجّلة مسبقًا بالصف المختار، "
            "مع الاحتفاظ بحساباتهن ونتائجهن.",
            "success",
        )
    if already_linked_count:
        flash(
            f"{already_linked_count} طالبة مسجّلة بالفعل في هذا الصف؛ لم يتكرر الربط.",
            "info",
        )
    if not invitation_urls:
        if not linked_count and not already_linked_count:
            flash(
                "لم تُنشأ دعوات جديدة. تحققي من أن العناوين تخص حسابات طالبات نشطات.",
                "warning",
            )
        return []

    if renewed_count:
        flash(
            f"تم تجديد {renewed_count} دعوة سابقة وإصدار روابط جديدة؛ "
            "سيُرسل النظام الروابط الجديدة إذا كانت إعدادات البريد الإلكتروني صحيحة.",
            "info",
        )

    if invitation_mail_settings():
        sent, failed = 0, []
        for item in invitation_urls:
            try:
                send_student_invitation(
                    item["email"],
                    item["url"],
                    current_user.full_name or "معلمة منصة الريان",
                )
                sent += 1
            except Exception:
                current_app.logger.exception(
                    "Could not email student invitation to %s", item["email"]
                )
                failed.append(item["email"])
        if failed:
            flash(
                f"تم حفظ {len(invitation_urls)} دعوة. قبل خادم البريد إرسال "
                f"{sent} رسالة، وفشل إرسال {len(failed)} رسالة. "
                "الروابط الجديدة متاحة للنسخ أدناه؛ راجعي سجل Render لإصلاح سبب الفشل.",
                "warning",
            )
        else:
            flash(
                f"قبل خادم البريد طلب إرسال {sent} رسالة. "
                "هذا لا يضمن وصولها إلى صندوق الوارد؛ إذا لم تصل، افحصي البريد غير المرغوب "
                "فيه وسجل مزوّد البريد.",
                "success",
            )
    else:
        flash(
            f"تم إنشاء {len(invitation_urls)} دعوة، لكن البريد غير مفعّل لأن إعدادات SMTP "
            "غير مكتملة في Render. الروابط الجديدة متاحة للنسخ أدناه.",
            "warning",
        )
    return invitation_urls


@platform_admin_bp.route("/resources", methods=["GET", "POST"])
def resources():
    form = LearningResourceForm(); form.lesson_id.choices = lesson_choices()
    if form.validate_on_submit():
        try:
            owned_lesson_or_404(form.lesson_id.data)
            original, path, relative = save_upload(form.document.data, "learning_resources", {"pdf", "doc", "docx", "png", "jpg", "jpeg"})
            resource = LearningResource(lesson_id=form.lesson_id.data, created_by_id=current_user.id, title=form.title.data.strip(), resource_type=form.resource_type.data, description=(form.description.data or "").strip() or None, original_filename=original, stored_path=relative, mime_type=form.document.data.mimetype, allow_download=form.allow_download.data, publication_status=form.publication_status.data)
            db.session.add(resource); db.session.commit(); flash("تم حفظ المحتوى التعليمي", "success")
            return redirect(url_for("platform_admin.resources"))
        except Exception as error:
            db.session.rollback(); flash(f"تعذر رفع الملف: {error}", "error")
    query = LearningResource.query if current_user.role == "admin" else LearningResource.query.filter_by(created_by_id=current_user.id)
    query = query.filter(LearningResource.lesson_id.in_(lesson_ids_for_grade(selected_management_grade()) or [-1]))
    return render_template("platform/resources.html", form=form, resources=query.order_by(LearningResource.created_at.desc()).all())


def owned_content_or_404(model, row_id):
    row = db.session.get(model, row_id)
    if row is None:
        abort(404)
    if current_user.role != "admin" and row.created_by_id != current_user.id:
        abort(403)
    if hasattr(row, "lesson_id") and row.lesson_id not in set(lesson_ids_for_grade(selected_management_grade())):
        abort(404)
    return row


@platform_admin_bp.post("/resources/<int:row_id>/toggle")
def toggle_resource(row_id):
    row = owned_content_or_404(LearningResource, row_id)
    row.publication_status = "draft" if row.publication_status == "published" else "published"
    db.session.commit()
    flash("تم تحديث ظهور الملف للطلاب.", "success")
    return redirect(url_for("platform_admin.resources"))


@platform_admin_bp.post("/resources/<int:row_id>/delete")
def delete_resource(row_id):
    row = owned_content_or_404(LearningResource, row_id)
    relative_path = row.stored_path
    db.session.delete(row)
    db.session.commit()
    if relative_path:
        target = (Path(current_app.config["UPLOAD_FOLDER"]) / relative_path).resolve()
        root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
        if target.is_relative_to(root) and target.is_file():
            target.unlink()
    flash("تم حذف الملف نهائيًا.", "success")
    return redirect(url_for("platform_admin.resources"))


@platform_admin_bp.route("/concept-maps", methods=["GET", "POST"])
def concept_maps():
    form = ConceptMapForm(); form.lesson_id.choices = lesson_choices()
    upload_form = ConceptMapUploadForm(prefix="upload"); upload_form.lesson_id.choices = lesson_choices()
    if form.validate_on_submit():
        try:
            graph = json.loads(form.nodes_json.data or "{}")
        except ValueError:
            graph = {}
        nodes_data = graph.get("nodes", []) if isinstance(graph, dict) else []
        edges_data = graph.get("edges", []) if isinstance(graph, dict) else []
        if len(nodes_data) < 2:
            form.nodes_json.errors.append("أضيفي مفهومين على الأقل داخل المصمم")
        else:
            owned_lesson_or_404(form.lesson_id.data)
            nodes_data = nodes_data[:80]
            edges_data = edges_data[:160]
            concept_map = ConceptMap(lesson_id=form.lesson_id.data, created_by_id=current_user.id, title=form.title.data.strip(), map_type="concept", creation_method="manual", publication_status=form.publication_status.data)
            db.session.add(concept_map); db.session.flush()
            nodes = {}
            for index, item in enumerate(nodes_data):
                label = str(item.get("label", "")).strip()[:250]
                if not label: continue
                try:
                    position_x = min(max(float(item.get("x", (index % 3) * 260)), 0), 2000)
                    position_y = min(max(float(item.get("y", (index // 3) * 150)), 0), 2000)
                except (TypeError, ValueError):
                    position_x, position_y = (index % 3) * 260, (index // 3) * 150
                node = ConceptMapNode(concept_map_id=concept_map.id, label=label, description=str(item.get("description", "")).strip()[:2000] or None, position_x=position_x, position_y=position_y)
                db.session.add(node); db.session.flush(); nodes[str(item.get("key", index))] = node
            for item in edges_data:
                source, target = nodes.get(str(item.get("source"))), nodes.get(str(item.get("target")))
                if source and target and source.id != target.id:
                    db.session.add(ConceptMapEdge(concept_map_id=concept_map.id, source_node_id=source.id, target_node_id=target.id, label=str(item.get("label", ""))[:150] or None))
            db.session.commit(); flash("تم إنشاء الخريطة المفاهيمية", "success")
            return redirect(_safe_admin_return_url("platform_admin.concept_maps"))
    query = ConceptMap.query if current_user.role == "admin" else ConceptMap.query.filter_by(created_by_id=current_user.id)
    query = query.filter(ConceptMap.lesson_id.in_(lesson_ids_for_grade(selected_management_grade()) or [-1]))
    status_filter = (request.args.get("status") or "all").strip().lower()
    if status_filter not in {"all", "draft", "published"}:
        status_filter = "all"
    if status_filter in {"draft", "published"}:
        query = query.filter_by(publication_status=status_filter)
    maps = query.order_by(ConceptMap.created_at.desc()).all()
    return render_template(
        "platform/concept_maps.html",
        form=form,
        upload_form=upload_form,
        maps=maps,
        status_filter=status_filter,
        editing_map=None,
    )


@platform_admin_bp.route("/concept-maps/<int:row_id>/edit", methods=["GET", "POST"])
def edit_manual_concept_map(row_id):
    """Edit a manually created concept map without replacing its identity or lesson history."""
    row = owned_content_or_404(ConceptMap, row_id)
    if row.creation_method != "manual":
        abort(404)

    form = ConceptMapForm(obj=row)
    form.lesson_id.choices = lesson_choices()
    upload_form = ConceptMapUploadForm(prefix="upload")
    upload_form.lesson_id.choices = lesson_choices()

    if request.method == "GET":
        form.lesson_id.data = row.lesson_id
        form.title.data = row.title
        form.publication_status.data = row.publication_status
        node_keys = {node.id: str(node.id) for node in row.nodes}
        form.nodes_json.data = json.dumps({
            "nodes": [
                {
                    "key": node_keys[node.id],
                    "label": node.label,
                    "description": node.description or "",
                    "tone": "gold",
                    "x": node.position_x or 0,
                    "y": node.position_y or 0,
                }
                for node in row.nodes
            ],
            "edges": [
                {
                    "source": node_keys[edge.source_node_id],
                    "target": node_keys[edge.target_node_id],
                    "label": edge.label or "يتفرع إلى",
                }
                for edge in row.edges
                if edge.source_node_id in node_keys and edge.target_node_id in node_keys
            ],
        }, ensure_ascii=False)

    if form.validate_on_submit():
        try:
            graph = json.loads(form.nodes_json.data or "{}")
        except (TypeError, ValueError):
            graph = {}
        nodes_data = graph.get("nodes", []) if isinstance(graph, dict) else []
        edges_data = graph.get("edges", []) if isinstance(graph, dict) else []
        if len(nodes_data) < 2:
            form.nodes_json.errors.append("أضيفي مفهومين على الأقل داخل المصمم")
        else:
            lesson = owned_lesson_or_404(form.lesson_id.data)
            row.lesson_id = lesson.id
            row.title = form.title.data.strip()
            row.publication_status = form.publication_status.data

            db.session.query(ConceptMapEdge).filter_by(concept_map_id=row.id).delete(synchronize_session=False)
            db.session.query(ConceptMapNode).filter_by(concept_map_id=row.id).delete(synchronize_session=False)
            db.session.flush()

            nodes = {}
            for index, item in enumerate(nodes_data[:80]):
                label = str(item.get("label", "")).strip()[:250]
                if not label:
                    continue
                try:
                    position_x = min(max(float(item.get("x", (index % 3) * 260)), 0), 2000)
                    position_y = min(max(float(item.get("y", (index // 3) * 150)), 0), 2000)
                except (TypeError, ValueError):
                    position_x, position_y = (index % 3) * 260, (index // 3) * 150
                node = ConceptMapNode(
                    concept_map_id=row.id,
                    label=label,
                    description=str(item.get("description", "")).strip()[:2000] or None,
                    position_x=position_x,
                    position_y=position_y,
                )
                db.session.add(node)
                db.session.flush()
                nodes[str(item.get("key", index))] = node

            for item in edges_data[:160]:
                source = nodes.get(str(item.get("source")))
                target = nodes.get(str(item.get("target")))
                if source and target and source.id != target.id:
                    db.session.add(ConceptMapEdge(
                        concept_map_id=row.id,
                        source_node_id=source.id,
                        target_node_id=target.id,
                        label=str(item.get("label", ""))[:150] or None,
                    ))

            db.session.commit()
            flash("تم حفظ تعديلات الخريطة المفاهيمية.", "success")
            return redirect(_safe_admin_return_url("platform_admin.concept_maps") + "#concept-map-library")

    query = ConceptMap.query if current_user.role == "admin" else ConceptMap.query.filter_by(created_by_id=current_user.id)
    query = query.filter(ConceptMap.lesson_id.in_(lesson_ids_for_grade(selected_management_grade()) or [-1]))
    maps = query.order_by(ConceptMap.created_at.desc()).all()
    return render_template(
        "platform/concept_maps.html",
        form=form,
        upload_form=upload_form,
        maps=maps,
        status_filter="all",
        editing_map=row,
    )


@platform_admin_bp.post("/concept-maps/upload")
def upload_concept_map():
    form = ConceptMapUploadForm(prefix="upload"); form.lesson_id.choices = lesson_choices()
    if not form.validate_on_submit():
        flash("راجعي بيانات خريطة الرفع وصيغة الملف.", "error")
        return redirect(url_for("platform_admin.concept_maps"))
    owned_lesson_or_404(form.lesson_id.data)
    try:
        original, path, relative = save_upload(
            form.document.data,
            "concept_maps",
            {"pdf", "png", "jpg", "jpeg", "webp"},
        )
    except Exception as error:
        current_app.logger.exception("Concept-map upload failed")
        flash(f"تعذر رفع الخريطة: {error}", "error")
        return redirect(url_for("platform_admin.concept_maps"))
    row = ConceptMap(lesson_id=form.lesson_id.data, created_by_id=current_user.id, title=form.title.data.strip(), map_type="uploaded", creation_method="upload", publication_status=form.publication_status.data, original_filename=original, stored_path=relative, mime_type=form.document.data.mimetype)
    db.session.add(row); db.session.commit()
    flash("تم رفع الخريطة الجاهزة.", "success")
    return redirect(url_for("platform_admin.concept_maps"))


def layout_concept_tree(node_by_key, edge_rows):
    """Store a tree-shaped layout so generated maps open as branches, not a grid."""
    children = {key: [] for key in node_by_key}
    targeted = set()
    for edge in edge_rows:
        source_key = str(edge.get("source"))
        target_key = str(edge.get("target"))
        if source_key in node_by_key and target_key in node_by_key and source_key != target_key:
            if target_key not in targeted:
                children[source_key].append(target_key)
                targeted.add(target_key)

    leaf_index = 0
    visited = set()

    def place(key, depth):
        nonlocal leaf_index
        if key in visited:
            return leaf_index * 155
        visited.add(key)
        node = node_by_key[key]
        node.position_x = depth * 300
        child_keys = [child for child in children.get(key, []) if child not in visited]
        if not child_keys:
            node.position_y = leaf_index * 155
            leaf_index += 1
            return node.position_y
        child_positions = [place(child, depth + 1) for child in child_keys]
        node.position_y = (child_positions[0] + child_positions[-1]) / 2
        return node.position_y

    roots = [key for key in node_by_key if key not in targeted]
    for key in roots:
        place(key, 0)
    for key in node_by_key:
        if key not in visited:
            place(key, 0)


@platform_admin_bp.post("/concept-maps/generate")
def generate_concept_map():
    lesson = owned_lesson_or_404(request.form.get("lesson_id", type=int))
    try:
        payload = generate_concept_map_draft(lesson)
        row = ConceptMap(
            lesson_id=lesson.id,
            created_by_id=current_user.id,
            title=payload.get("title") or f"خريطة {lesson.title}",
            map_type="concept",
            creation_method="ai",
            publication_status="draft",
        )
        db.session.add(row)
        db.session.flush()
        node_by_key = {}
        for item in payload["nodes"]:
            label = str(item.get("label", "")).strip()[:250]
            if not label:
                continue
            node = ConceptMapNode(
                concept_map_id=row.id,
                label=label,
                description=str(item.get("description", "")).strip() or None,
                position_x=0,
                position_y=0,
            )
            db.session.add(node)
            db.session.flush()
            node_key = str(item.get("key") or f"n{len(node_by_key) + 1}")
            while node_key in node_by_key:
                node_key = f"{node_key}-{len(node_by_key) + 1}"
            node_by_key[node_key] = node

        if len(node_by_key) < 2:
            raise RuntimeError("لم ينتج المقترح مفاهيم كافية لبناء شجرة.")

        # Normalize the AI relationships into a real tree: one root and one parent per node.
        node_keys = list(node_by_key)
        root_key = node_keys[0]
        tree_edges = []
        parent_by_target = {}
        for edge in payload["edges"]:
            source_key = str(edge.get("source"))
            target_key = str(edge.get("target"))
            if (
                source_key not in node_by_key
                or target_key not in node_by_key
                or source_key == target_key
                or target_key == root_key
                or target_key in parent_by_target
            ):
                continue
            cursor = source_key
            creates_cycle = False
            while cursor in parent_by_target:
                if cursor == target_key:
                    creates_cycle = True
                    break
                cursor = parent_by_target[cursor]
            if creates_cycle:
                continue
            tree_edges.append({
                "source": source_key,
                "target": target_key,
                "label": str(edge.get("label", ""))[:150] or "",
            })
            parent_by_target[target_key] = source_key

        # Attach any disconnected concepts to the root so the result is never a loose grid.
        for key in node_keys[1:]:
            if key not in parent_by_target:
                tree_edges.append({"source": root_key, "target": key, "label": "فرع"})
                parent_by_target[key] = root_key

        for edge in tree_edges:
            source = node_by_key[edge["source"]]
            target = node_by_key[edge["target"]]
            db.session.add(ConceptMapEdge(
                concept_map_id=row.id,
                source_node_id=source.id,
                target_node_id=target.id,
                label=edge["label"] or None,
            ))

        layout_concept_tree(node_by_key, tree_edges)
        db.session.commit()
        flash("أنشأ الذكاء الاصطناعي خريطة شجرية كمسودة. راجعيها قبل نشرها.", "success")
    except Exception as error:
        db.session.rollback()
        current_app.logger.exception("Concept map AI generation failed")
        flash(f"تعذر إنشاء الخريطة: {error}", "error")
    return redirect(url_for("platform_admin.concept_maps") + "#concept-map-library")


@platform_admin_bp.post("/concept-maps/<int:row_id>/toggle")
def toggle_concept_map(row_id):
    row = owned_content_or_404(ConceptMap, row_id)
    row.publication_status = "draft" if row.publication_status == "published" else "published"
    db.session.commit()
    flash("تم تحديث حالة الخريطة.", "success")
    return redirect(url_for("platform_admin.concept_maps"))


@platform_admin_bp.post("/concept-maps/<int:row_id>/delete")
def delete_concept_map(row_id):
    row = owned_content_or_404(ConceptMap, row_id)
    relative_path = row.stored_path
    db.session.delete(row)
    db.session.commit()

    if relative_path:
        root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
        target = (root / relative_path).resolve()
        if target.is_relative_to(root) and target.is_file():
            try:
                target.unlink()
            except OSError:
                current_app.logger.warning("Could not remove concept map file %s", target)

    flash("تم حذف الخريطة المفاهيمية.", "success")
    return redirect(url_for("platform_admin.concept_maps"))


@platform_admin_bp.route("/characters", methods=["GET", "POST"])
def characters():
    form = HistoricalCharacterForm(); form.lesson_id.choices = lesson_choices()
    if form.validate_on_submit():
        db.session.add(HistoricalCharacter(lesson_id=form.lesson_id.data, created_by_id=current_user.id, name=form.name.data.strip(), period=(form.period.data or "").strip() or None, summary=form.summary.data.strip(), key_events=(form.key_events.data or "").strip() or None, clues=(form.clues.data or "").strip() or None, source_notes=(form.source_notes.data or "").strip() or None, publication_status=form.publication_status.data))
        db.session.commit(); flash("تم حفظ الشخصية التاريخية", "success")
        return redirect(url_for("platform_admin.characters"))
    query = HistoricalCharacter.query if current_user.role == "admin" else HistoricalCharacter.query.filter_by(created_by_id=current_user.id)
    query = query.filter(HistoricalCharacter.lesson_id.in_(lesson_ids_for_grade(selected_management_grade()) or [-1]))
    return render_template("platform/characters.html", form=form, characters=query.order_by(HistoricalCharacter.created_at.desc()).all())


@platform_admin_bp.post("/characters/generate")
def generate_characters():
    lesson = db.session.get(Lesson, request.form.get("lesson_id", type=int))
    if lesson is None or lesson not in teacher_lessons():
        abort(404)
    try:
        drafts, citations = generate_character_drafts(lesson)
        created = 0
        for item in drafts:
            name = str(item.get("name", "")).strip()
            summary = str(item.get("summary", "")).strip()
            if not name or not summary or HistoricalCharacter.query.filter_by(lesson_id=lesson.id, name=name).first():
                continue
            clues = item.get("who_am_i_clues") or []
            notes = "\n".join(citations)
            db.session.add(HistoricalCharacter(
                lesson_id=lesson.id,
                created_by_id=current_user.id,
                name=name[:200],
                period=str(item.get("period", "")).strip()[:150] or None,
                summary=summary[:5000],
                key_events="\n".join(str(event) for event in (item.get("key_events") or []))[:5000] or None,
                source_notes=notes[:2000],
                clues="\n".join(str(clue) for clue in clues)[:3000] or None,
                publication_status="draft",
                is_ai_generated=True,
            ))
            created += 1
        db.session.commit()
        flash(f"تم حفظ {created} شخصية كمسودات للمراجعة.", "success")
    except Exception as error:
        db.session.rollback()
        current_app.logger.exception("Character AI generation failed")
        flash(f"تعذر استخراج الشخصيات: {error}", "error")
    return redirect(url_for("platform_admin.characters"))


@platform_admin_bp.route("/characters/<int:row_id>/edit", methods=["GET", "POST"])
def edit_character(row_id):
    row = owned_content_or_404(HistoricalCharacter, row_id)
    form = HistoricalCharacterForm(obj=row)
    form.lesson_id.choices = lesson_choices()
    if form.validate_on_submit():
        row.lesson_id = form.lesson_id.data
        row.name = form.name.data.strip()
        row.period = (form.period.data or "").strip() or None
        row.summary = form.summary.data.strip()
        row.key_events = (form.key_events.data or "").strip() or None
        row.clues = (form.clues.data or "").strip() or None
        row.source_notes = (form.source_notes.data or "").strip() or None
        row.publication_status = form.publication_status.data
        db.session.commit()
        flash("تمت مراجعة الشخصية وحفظها.", "success")
        return redirect(url_for("platform_admin.characters"))
    return render_template("platform/edit_character.html", form=form, character=row)


@platform_admin_bp.post("/characters/<int:row_id>/toggle")
def toggle_character(row_id):
    row = owned_content_or_404(HistoricalCharacter, row_id)
    row.publication_status = "draft" if row.publication_status == "published" else "published"
    db.session.commit()
    flash("تم تحديث ظهور الشخصية للطلاب.", "success")
    return redirect(url_for("platform_admin.characters"))


@platform_admin_bp.route("/settings", methods=["GET", "POST"])
def settings():
    row = PlatformSettings.get_or_create()
    form = PlatformSettingsForm(obj=row)

    if form.validate_on_submit():
        entered_whatsapp = (form.whatsapp_url.data or "").strip()
        whatsapp_value = None

        if entered_whatsapp:
            # Keep only secure, direct WhatsApp links from trusted WhatsApp domains.
            from urllib.parse import urlparse

            if entered_whatsapp.lower().startswith(("https://", "http://")):
                parsed = urlparse(entered_whatsapp)
                allowed_hosts = {
                    "wa.me",
                    "www.wa.me",
                    "api.whatsapp.com",
                    "chat.whatsapp.com",
                    "web.whatsapp.com",
                }
                if parsed.scheme == "https" and parsed.hostname and parsed.hostname.lower() in allowed_hosts:
                    whatsapp_value = entered_whatsapp
                else:
                    form.whatsapp_url.errors.append(
                        "أدخلي رقمًا مع مفتاح الدولة أو رابط واتساب مباشر يبدأ بـ https ومن نطاق واتساب."
                    )
                    return render_template("platform/settings.html", form=form)
            elif re.fullmatch(r"[\d\s()+.\-]+", entered_whatsapp):
                digits = re.sub(r"\D", "", entered_whatsapp)
                if digits.startswith("00"):
                    digits = digits[2:]
                elif digits.startswith("0"):
                    digits = "970" + digits[1:]

                if 8 <= len(digits) <= 15:
                    whatsapp_value = f"https://wa.me/{digits}"
                else:
                    form.whatsapp_url.errors.append(
                        "تأكدي من رقم واتساب ومفتاح الدولة؛ يجب أن يكون الرقم بين 8 و15 رقمًا."
                    )
                    return render_template("platform/settings.html", form=form)
            else:
                form.whatsapp_url.errors.append(
                    "أدخلي رقمًا فقط مع مفتاح الدولة أو رابط واتساب مباشر."
                )
                return render_template("platform/settings.html", form=form)

        try:
            row.platform_name = form.platform_name.data.strip()
            row.tagline = form.tagline.data.strip()
            row.whatsapp_url = whatsapp_value
            row.support_email = (form.support_email.data or "").strip() or None
            db.session.commit()
            flash("تم حفظ إعدادات المنصة وتحديث رابط واتساب.", "success")
            return redirect(url_for("platform_admin.settings"))
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Platform settings save failed")
            flash("تعذر حفظ الإعدادات. لم يتم اعتماد التغييرات؛ حاولي مرة أخرى.", "error")

    return render_template("platform/settings.html", form=form)


@platform_admin_bp.route("/admins", methods=["GET", "POST"])
def admins():
    """Only the two platform owners may create or review admin accounts."""
    if not is_platform_owner(current_user):
        abort(403)

    if request.method == "POST":
        full_name = (request.form.get("full_name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        if len(full_name) < 2 or len(full_name) > 150:
            flash("اكتبي اسمًا كاملًا صحيحًا.", "error")
        elif len(email) > 255 or email.count("@") != 1 or "." not in email.rsplit("@", 1)[-1] or any(char.isspace() for char in email):
            flash("تحققي من صيغة البريد الإلكتروني.", "error")
        elif len(password) < 12 or len(password) > 128:
            flash("كلمة مرور الإدارة يجب أن تحتوي على 12 حرفًا على الأقل.", "error")
        elif User.query.filter_by(email=email).first():
            flash("هذا البريد مستخدم بالفعل. لم يتم تغيير أي حساب.", "error")
        else:
            account = User(
                full_name=full_name,
                email=email,
                role="admin",
                is_active_account=True,
            )
            account.set_password(password)
            db.session.add(account)
            db.session.commit()
            flash("تم إنشاء حساب الإدارة بنجاح.", "success")
            return redirect(url_for("platform_admin.admins"))

    admins = User.query.filter_by(role="admin").order_by(User.created_at.asc()).all()
    owner_emails = sorted(platform_owner_emails())
    owner_accounts = {
        (account.email or "").strip().casefold(): account
        for account in User.query.filter(func.lower(User.email).in_(owner_emails)).all()
    }
    return render_template(
        "platform/admins.html",
        admins=admins,
        owner_emails=owner_emails,
        owner_accounts=owner_accounts,
        primary_owner_email="1shahdmohammed@gmail.com",
    )


@platform_admin_bp.post("/admins/<int:admin_id>/remove")
def remove_admin_privilege(admin_id):
    """Remove admin privileges without deleting the account or its linked data."""
    if not is_platform_owner(current_user):
        abort(403)
    account = User.query.filter_by(id=admin_id, role="admin").first_or_404()
    email = (account.email or "").strip().casefold()
    if email in platform_owner_emails() or account.id == current_user.id:
        flash("لا يمكن إزالة صلاحية الإدارة عن حساب مالكة المنصة أو الحساب الذي تستخدمينه الآن.", "error")
        return redirect(url_for("platform_admin.admins"))
    account.role = "teacher"
    db.session.commit()
    flash("تمت إزالة صلاحية الإدارة عن الحساب. بقي الحساب ومحتواه وسجلاته محفوظة دون حذف.", "success")
    return redirect(url_for("platform_admin.admins"))


@platform_admin_bp.post("/admins/<int:admin_id>/delete")
def delete_admin_account(admin_id):
    """Delete an eligible admin login while preserving authored platform content."""
    if not is_platform_owner(current_user):
        abort(403)

    account = User.query.filter_by(id=admin_id, role="admin").first_or_404()
    email = (account.email or "").strip().casefold()
    protected_emails = platform_owner_emails()
    if account.id == current_user.id or email in protected_emails:
        flash("لا يمكن حذف حساب الإدارة الأساسي أو أحد حسابات مالكات المنصة.", "error")
        return redirect(url_for("platform_admin.admins"))

    # Never cascade-delete a person's learning history or student records.
    learner_history_checks = [
        (WorksheetAttempt, "student_id"),
        (DateReview, "student_id"),
        (XPTransaction, "student_id"),
        (ClassEnrollment, "student_id"),
        (TutorConversation, "student_id"),
        (ConceptMastery, "student_id"),
        (CharacterAttempt, "student_id"),
        (HonorBoardEntry, "student_id"),
        (LearningPlanItem, "student_id"),
    ]
    for model, field_name in learner_history_checks:
        if hasattr(model, field_name) and model.query.filter(
            getattr(model, field_name) == account.id
        ).first():
            flash("لا يمكن حذف هذا الحساب بأمان لوجود سجلات تعلّم مرتبطة به. أزيلي صلاحية الإدارة بدلًا من حذف السجلات.", "error")
            return redirect(url_for("platform_admin.admins"))

    try:
        # Preserve content and invitations by transferring their ownership to
        # the authenticated platform owner before removing the login account.
        for model in (Curriculum, LearningResource, ConceptMap, HistoricalCharacter, Worksheet, Classroom, StudentInvitation):
            if hasattr(model, "created_by_id"):
                model.query.filter_by(created_by_id=account.id).update(
                    {"created_by_id": current_user.id},
                    synchronize_session=False,
                )
        db.session.delete(account)
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Admin account deletion failed for account id %s", admin_id)
        flash("تعذر حذف الحساب لأن هناك سجلات مرتبطة به لا يمكن نقلها بأمان. لم يتم اعتماد الحذف.", "error")
        return redirect(url_for("platform_admin.admins"))

    flash("تم حذف حساب الإدارة وتحرير البريد الإلكتروني للتسجيل من جديد، مع الحفاظ على المحتوى الذي كان مرتبطًا به.", "success")
    return redirect(url_for("platform_admin.admins"))


@platform_admin_bp.post("/admins/owners/<int:account_id>/activate")
def activate_platform_owner_account(account_id):
    """Restore admin access only for one of the two configured owner emails."""
    if not is_platform_owner(current_user):
        abort(403)
    account = User.query.filter_by(id=account_id).first_or_404()
    email = (account.email or "").strip().casefold()
    if email not in platform_owner_emails():
        abort(403)
    account.role = "admin"
    account.is_active_account = True
    db.session.commit()
    flash(f"تم تفعيل صلاحيات الإدارة للحساب {email}.", "success")
    return redirect(url_for("platform_admin.admins"))


@platform_admin_bp.get("/analytics")
def analytics():
    """Summarize assessment, practice, AI tutor, character, and points activity."""
    grade_lesson_ids = lesson_ids_for_grade(selected_management_grade())
    worksheet_query = Worksheet.query.filter(Worksheet.lesson_id.in_(grade_lesson_ids or [-1]))
    if current_user.role != "admin":
        worksheet_query = worksheet_query.filter_by(created_by_id=current_user.id)
    owned_worksheets = worksheet_query.all()
    worksheet_ids = [item.id for item in owned_worksheets]

    classroom_query = Classroom.query.filter(Classroom.id.in_(classroom_ids_for_grade(selected_management_grade(), teacher_id=None if current_user.role == "admin" else current_user.id, active_only=False) or [-1]))
    classrooms = classroom_query.all()
    student_ids = {
        enrollment.student_id
        for classroom in classrooms
        for enrollment in classroom.enrollments
    }

    if worksheet_ids:
        student_ids.update(
            student_id for (student_id,) in
            db.session.query(WorksheetAttempt.student_id)
            .filter(WorksheetAttempt.worksheet_id.in_(worksheet_ids))
            .distinct().all()
        )

    if current_user.role == "admin":
        student_ids.update(student_ids_for_grade(selected_management_grade(), active_only=True))

    allowed_grade_students = set(student_ids_for_grade(
        selected_management_grade(),
        teacher_id=None if current_user.role == "admin" else current_user.id,
        active_only=True,
    ))
    student_ids.intersection_update(allowed_grade_students)

    students = (
        User.query.filter(User.id.in_(student_ids), User.role == "student")
        .order_by(User.full_name).all()
        if student_ids else []
    )
    scoped_student_ids = [student.id for student in students]

    all_attempts = []
    if scoped_student_ids:
        all_attempts = WorksheetAttempt.query.join(Worksheet).filter(
            WorksheetAttempt.student_id.in_(scoped_student_ids),
            Worksheet.lesson_id.in_(grade_lesson_ids or [-1]),
        ).all()

    all_transactions = (
        XPTransaction.query.filter(
            XPTransaction.student_id.in_(scoped_student_ids)
        ).all()
        if scoped_student_ids else []
    )

    rows = []
    for student in students:
        student_all_attempts = [
            attempt for attempt in all_attempts
            if attempt.student_id == student.id
        ]
        student_attempts = [
            attempt for attempt in student_all_attempts
            if attempt.submitted_at is not None
        ]
        test_attempts = [
            attempt for attempt in student_attempts
            if attempt.worksheet and attempt.worksheet.creation_method == "test"
        ]
        worksheet_attempts = [
            attempt for attempt in student_attempts
            if not attempt.worksheet or attempt.worksheet.creation_method != "test"
        ]
        # لا ندخل المحاولات التي تنتظر تصحيحًا يدويًا في متوسط النتائج.
        graded_attempts = [
            attempt for attempt in student_attempts
            if not any(answer.is_correct is None for answer in attempt.answers)
        ]
        percentages = [attempt.percentage for attempt in graded_attempts]
        mastery_rows = ConceptMastery.query.filter(
            ConceptMastery.student_id == student.id,
            ConceptMastery.lesson_id.in_(grade_lesson_ids or [-1]),
        ).all()
        challenge_sessions = ChallengeSession.query.filter(
            ChallengeSession.student_id == student.id,
            ChallengeSession.lesson_id.in_(grade_lesson_ids or [-1]),
        ).all()
        challenges = [session for session in challenge_sessions if session.status == "completed"]
        tutor_interactions = TutorMessage.query.join(TutorConversation).filter(
            TutorConversation.student_id == student.id,
            TutorMessage.role == "student",
        ).count()
        character_attempts = CharacterAttempt.query.join(HistoricalCharacter).filter(
            CharacterAttempt.student_id == student.id,
            HistoricalCharacter.lesson_id.in_(grade_lesson_ids or [-1]),
        ).count()
        date_reviews = DateReview.query.join(HistoricalDate).filter(
            DateReview.student_id == student.id,
            HistoricalDate.lesson_id.in_(grade_lesson_ids or [-1]),
        ).count()
        plan_items = LearningPlanItem.query.filter(
            LearningPlanItem.student_id == student.id,
            LearningPlanItem.lesson_id.in_(grade_lesson_ids or [-1]),
        ).all()
        plan_verifications = sum(1 for item in plan_items if item.verified_at is not None)
        student_transactions = [
            transaction for transaction in all_transactions
            if transaction.student_id == student.id
        ]
        resource_downloads = sum(1 for transaction in student_transactions if transaction.reason == "resource_downloaded")
        concept_map_views = sum(1 for transaction in student_transactions if transaction.reason == "concept_map_viewed")
        library_visits = sum(1 for transaction in student_transactions if transaction.reason == "learning_library_opened")
        points_earned = sum(transaction.amount for transaction in student_transactions)
        # Count every saved answer, not only answers that earned XP.
        # XP transactions are a reward ledger and intentionally omit zero-point answers.
        challenge_answers = sum(
            1
            for session in challenge_sessions
            for question in session.questions
            if question.answer is not None
        )
        tutor_evaluated_answers = TutorMessage.query.join(TutorConversation).filter(
            TutorConversation.student_id == student.id,
            TutorConversation.lesson_id.in_(grade_lesson_ids or [-1]),
            TutorMessage.role == "tutor",
            TutorMessage.evaluation.in_([
                "correct", "partially_correct", "incorrect", "needs_explanation"
            ]),
        ).count()
        average = round(sum(percentages) / len(percentages), 1) if percentages else 0.0
        mastery_average = (
            round(sum(item.mastery_score for item in mastery_rows) / len(mastery_rows), 1)
            if mastery_rows else 0.0
        )
        activity_score = (
            len(student_all_attempts) + len(challenge_sessions) + tutor_interactions
            + character_attempts + date_reviews + plan_verifications + resource_downloads
            + concept_map_views + library_visits + challenge_answers
            + tutor_evaluated_answers
        )
        rows.append({
            "student": student,
            "test_count": len(test_attempts),
            "worksheet_count": len(worksheet_attempts),
            "average": average,
            "mastery_average": mastery_average,
            "challenge_count": len(challenges),
            "challenge_answers": challenge_answers,
            "tutor_interactions": tutor_interactions,
            "tutor_evaluated_answers": tutor_evaluated_answers,
            "character_attempts": character_attempts,
            "date_reviews": date_reviews,
            "plan_items": len(plan_items),
            "plan_verifications": plan_verifications,
            "resource_downloads": resource_downloads,
            "concept_map_views": concept_map_views,
            "library_visits": library_visits,
            "points_earned": points_earned,
            "activity_score": activity_score,
            "has_results": bool(percentages),
            "needs_support": (
                (bool(percentages) and average < 50)
                or (bool(mastery_rows) and mastery_average < 50)
            ),
        })

    rows.sort(
        key=lambda item: (item["activity_score"], item["average"]),
        reverse=True,
    )
    # Pearson correlation helps visualize whether participation and achievement
    # tend to move together; it is descriptive, not proof of causation.
    # احسبي الارتباط من الطالبات اللاتي لديهن نتائج مكتملة فقط؛ لا نعامل غياب النتيجة كعلامة صفرية.
    correlation = None
    correlation_label = "تحتاج اللوحة إلى نتائج فعلية لثلاث طالبات على الأقل"
    correlation_rows = [row for row in rows if row["has_results"]]
    if len(correlation_rows) >= 3:
        activity_values = [float(row["activity_score"]) for row in correlation_rows]
        score_values = [float(row["average"]) for row in correlation_rows]
        activity_mean = sum(activity_values) / len(activity_values)
        score_mean = sum(score_values) / len(score_values)
        covariance = sum(
            (x - activity_mean) * (y - score_mean)
            for x, y in zip(activity_values, score_values)
        )
        activity_variance = sum((x - activity_mean) ** 2 for x in activity_values)
        score_variance = sum((y - score_mean) ** 2 for y in score_values)
        denominator = (activity_variance * score_variance) ** 0.5
        if denominator:
            correlation = round(max(-1.0, min(1.0, covariance / denominator)), 3)
            if correlation >= 0.25:
                correlation_label = "علاقة طردية ملحوظة في البيانات المتاحة"
            elif correlation <= -0.25:
                correlation_label = "علاقة عكسية ملحوظة في البيانات المتاحة"
            else:
                correlation_label = "العلاقة ضعيفة أو غير واضحة في البيانات المتاحة"
        else:
            correlation_label = "لا يظهر اتجاه واضح؛ أحد المتغيرين لا يتغير بين الطالبات";
    elif len(correlation_rows) > 0:
        correlation_label = "البيانات الحالية قليلة؛ نحتاج نتائج ثلاث طالبات على الأقل";

    submitted_attempts = [attempt for attempt in all_attempts if attempt.submitted_at is not None]
    graded_submitted_attempts = [
        attempt for attempt in submitted_attempts
        if not any(answer.is_correct is None for answer in attempt.answers)
    ]
    class_percentages = [attempt.percentage or 0 for attempt in graded_submitted_attempts]
    total_tutor_interactions = sum(row["tutor_interactions"] for row in rows)
    total_character_attempts = sum(row["character_attempts"] for row in rows)
    total_date_reviews = sum(row["date_reviews"] for row in rows)
    total_plan_verifications = sum(row["plan_verifications"] for row in rows)
    overview = {
        "students": len(students),
        "worksheets": sum(1 for item in owned_worksheets if item.creation_method != "test"),
        "tests": sum(1 for item in owned_worksheets if item.creation_method == "test"),
        "submissions": len(submitted_attempts),
        "average": round(sum(class_percentages) / len(class_percentages), 1)
        if class_percentages else 0.0,
        "challenge_completions": sum(row["challenge_count"] for row in rows),
        "tutor_interactions": total_tutor_interactions,
        "challenge_answers": sum(row["challenge_answers"] for row in rows),
        "tutor_evaluated_answers": sum(row["tutor_evaluated_answers"] for row in rows),
        "character_attempts": total_character_attempts,
        "date_reviews": total_date_reviews,
        "plan_verifications": total_plan_verifications,
        "resource_downloads": sum(row["resource_downloads"] for row in rows),
        "concept_map_views": sum(row["concept_map_views"] for row in rows),
        "library_visits": sum(row["library_visits"] for row in rows),
        "points_awarded": sum(transaction.amount for transaction in all_transactions),
        "support_count": sum(1 for row in rows if row["needs_support"]),
    }
    activity_max = max((row["activity_score"] for row in rows), default=1) or 1
    return render_template("platform/analytics.html", rows=rows, overview=overview, activity_max=activity_max, correlation=correlation, correlation_label=correlation_label)


@platform_admin_bp.route("/honor-board", methods=["GET", "POST"])
def honor_board():
    classrooms_query = Classroom.query.filter(Classroom.id.in_(classroom_ids_for_grade(selected_management_grade(), teacher_id=None if current_user.role == "admin" else current_user.id, active_only=True) or [-1]))
    classrooms = classrooms_query.all()
    student_ids = {
        enrollment.student_id
        for classroom in classrooms
        for enrollment in classroom.enrollments
    }

    if current_user.role == "admin":
        student_ids.update(student_ids_for_grade(selected_management_grade(), active_only=True))
    else:
        # Include active students who have submitted work in this teacher's
        # assessments, even if a class enrollment has not been linked yet.
        teacher_worksheet_ids = db.session.query(Worksheet.id).filter(
            Worksheet.created_by_id == current_user.id,
            Worksheet.lesson_id.in_(lesson_ids_for_grade(selected_management_grade()) or [-1]),
        )
        student_ids.update(
            student_id for (student_id,) in
            db.session.query(WorksheetAttempt.student_id)
            .filter(WorksheetAttempt.worksheet_id.in_(teacher_worksheet_ids))
            .distinct().all()
        )

    allowed_grade_students = set(student_ids_for_grade(
        selected_management_grade(),
        teacher_id=None if current_user.role == "admin" else current_user.id,
        active_only=True,
    ))
    student_ids.intersection_update(allowed_grade_students)

    students = (
        User.query.filter(
            User.id.in_(student_ids),
            User.role == "student",
            User.is_active_account.is_(True),
        ).order_by(User.full_name).all()
        if student_ids else []
    )
    allowed_student_ids = {student.id for student in students}

    if request.method == "POST":
        student_id = request.form.get("student_id", type=int)
        if student_id not in allowed_student_ids:
            abort(403)
        entry = HonorBoardEntry(
            teacher_id=current_user.id,
            student_id=student_id,
            category=request.form.get("category", "teacher_choice")[:50],
            note=(request.form.get("note") or "").strip()[:300] or None,
            period_label=(request.form.get("period_label") or "").strip()[:100] or None,
        )
        db.session.add(entry)
        db.session.commit()
        flash("تمت إضافة الطالبة إلى لوحة الشرف.", "success")
        return redirect(url_for("platform_admin.honor_board"))

    entries = HonorBoardEntry.query.filter(
        HonorBoardEntry.teacher_id == current_user.id,
        HonorBoardEntry.is_active.is_(True),
        HonorBoardEntry.student_id.in_(allowed_student_ids or [-1]),
    ).order_by(HonorBoardEntry.created_at.desc()).all()
    return render_template(
        "platform/honor_board.html",
        students=students,
        entries=entries,
    )


@platform_admin_bp.post("/honor-board/<int:entry_id>/remove")
def remove_honor_entry(entry_id):
    row = HonorBoardEntry.query.filter_by(id=entry_id, teacher_id=current_user.id).first_or_404()
    if row.student_id not in set(student_ids_for_grade(selected_management_grade(), teacher_id=current_user.id)):
        abort(404)
    row.is_active = False
    db.session.commit(); flash("تمت إزالة البطاقة من لوحة الشرف.", "success")
    return redirect(url_for("platform_admin.honor_board"))



@platform_admin_bp.route("/historical-dates", methods=["GET", "POST"])
def historical_dates():
    """Let teachers curate the dates and events used in student recall practice."""
    lessons = teacher_lessons()
    lesson_by_id = {lesson.id: lesson for lesson in lessons}
    lesson_ids = list(lesson_by_id)

    if request.method == "POST":
        lesson_id = request.form.get("lesson_id", type=int)
        if lesson_id not in lesson_by_id:
            abort(403)

        date_label = (request.form.get("date_label") or "").strip()[:100]
        event_title = (request.form.get("event_title") or "").strip()[:250]
        if not date_label or not event_title:
            flash("اكتبي التاريخ والحدث المرتبط به.", "error")
            return redirect(url_for("platform_admin.historical_dates"))

        sort_year = request.form.get("sort_year", type=int)
        importance_level = request.form.get("importance_level", type=int) or 1
        row = HistoricalDate(
            lesson_id=lesson_id,
            date_label=date_label,
            sort_year=sort_year,
            event_title=event_title,
            event_description=(request.form.get("event_description") or "").strip()[:3000] or None,
            memory_hint=(request.form.get("memory_hint") or "").strip()[:500] or None,
            importance_level=min(max(importance_level, 1), 3),
            is_published=request.form.get("is_published") == "on",
        )
        db.session.add(row)
        db.session.commit()
        flash("تم حفظ بطاقة التاريخ. إذا اخترتِ النشر فستظهر للطالبات في ذاكرة التواريخ.", "success")
        return redirect(url_for("platform_admin.historical_dates"))

    dates = []
    if lesson_ids:
        dates = (
            HistoricalDate.query
            .filter(HistoricalDate.lesson_id.in_(lesson_ids))
            .order_by(HistoricalDate.sort_year.asc(), HistoricalDate.id.desc())
            .all()
        )
    return render_template("platform/historical_dates.html", lessons=lessons, dates=dates)


@platform_admin_bp.post("/historical-dates/<int:date_id>/toggle")
def toggle_historical_date(date_id):
    lesson_ids = [lesson.id for lesson in teacher_lessons()]
    row = HistoricalDate.query.filter_by(id=date_id).first_or_404()
    if row.lesson_id not in lesson_ids:
        abort(403)
    row.is_published = not row.is_published
    db.session.commit()
    flash("تم تحديث حالة نشر التاريخ.", "success")
    return redirect(url_for("platform_admin.historical_dates"))


@platform_admin_bp.post("/historical-dates/<int:date_id>/delete")
def delete_historical_date(date_id):
    lesson_ids = [lesson.id for lesson in teacher_lessons()]
    row = HistoricalDate.query.filter_by(id=date_id).first_or_404()
    if row.lesson_id not in lesson_ids:
        abort(403)
    db.session.delete(row)
    db.session.commit()
    flash("تم حذف بطاقة التاريخ وسجل مراجعتها.", "success")
    return redirect(url_for("platform_admin.historical_dates"))