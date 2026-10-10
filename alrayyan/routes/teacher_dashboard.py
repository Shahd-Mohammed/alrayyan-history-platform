from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from uuid import uuid4

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from alrayyan.extensions import db
from alrayyan.forms import (
    AboutPageForm,
    EditWorksheetForm,
    UploadWorksheetForm,
)
from alrayyan.models import (
    AboutPage,
    Curriculum,
    Lesson,
    Unit,
    Worksheet,
    WorksheetAttachment,
)


teacher_dashboard_bp = Blueprint(
    "teacher_dashboard",
    __name__,
    url_prefix="/teacher-dashboard",
)


def teacher_required(view_function):
    """
    Allow only teachers and administrators to access
    teacher-dashboard pages.
    """

    @wraps(view_function)
    @login_required
    def wrapped_view(*args, **kwargs):
        if current_user.role not in {
            "teacher",
            "admin",
        }:
            abort(403)

        return view_function(*args, **kwargs)

    return wrapped_view


def get_teacher_worksheet_or_404(worksheet_id):
    """
    Return a worksheet owned by the current teacher.

    Administrators may access all worksheets.
    """

    worksheet = db.session.get(
        Worksheet,
        worksheet_id,
    )

    if worksheet is None:
        abort(404)

    if (
        current_user.role != "admin"
        and worksheet.created_by_id
        != current_user.id
    ):
        abort(403)

    return worksheet


def get_allowed_extensions():
    """
    Return the file extensions allowed by the application.
    """

    configured_extensions = current_app.config.get(
        "ALLOWED_WORKSHEET_EXTENSIONS",
        {
            "pdf",
            "doc",
            "docx",
            "png",
            "jpg",
            "jpeg",
        },
    )

    return {
        extension.lower().lstrip(".")
        for extension in configured_extensions
    }


def save_uploaded_file(
    uploaded_file,
    destination_folder,
):
    """
    Validate and save an uploaded worksheet file.

    The original Arabic filename is kept in the database.
    The stored file receives a safe UUID filename.
    """

    original_filename = (
        uploaded_file.filename or ""
    ).strip()

    if not original_filename:
        raise ValueError(
            "يرجى اختيار ملف صالح."
        )

    extension = (
        Path(original_filename)
        .suffix
        .lower()
        .lstrip(".")
    )

    if not extension:
        raise ValueError(
            "الملف لا يحتوي على امتداد معروف."
        )

    allowed_extensions = get_allowed_extensions()

    if extension not in allowed_extensions:
        raise ValueError(
            "نوع الملف غير مسموح. "
            "الأنواع المتاحة: PDF، Word، PNG، JPG."
        )

    stored_filename = (
        f"{uuid4().hex}.{extension}"
    )

    upload_root = Path(
        current_app.config["UPLOAD_FOLDER"]
    )

    destination_path = (
        upload_root / destination_folder
    )

    destination_path.mkdir(
        parents=True,
        exist_ok=True,
    )

    full_path = (
        destination_path / stored_filename
    )

    uploaded_file.save(full_path)

    file_size = full_path.stat().st_size

    relative_path = str(
        Path(destination_folder)
        / stored_filename
    )

    return {
        "original_filename": original_filename,
        "stored_filename": stored_filename,
        "storage_path": relative_path,
        "file_extension": extension,
        "mime_type": uploaded_file.mimetype,
        "file_size": file_size,
    }


@teacher_dashboard_bp.get("/")
@teacher_required
def dashboard():
    """
    Display the teacher dashboard and all worksheets
    created by the current teacher.
    """

    query = Worksheet.query

    if current_user.role != "admin":
        query = query.filter_by(
            created_by_id=current_user.id,
        )

    active_query = query.filter_by(is_archived=False)
    total_count = active_query.count()
    published_count = active_query.filter(Worksheet.publication_status == "published").count()
    draft_count = active_query.filter(Worksheet.publication_status == "draft").count()
    search_term = (request.args.get("q") or "").strip()
    status_filter = (request.args.get("status") or "").strip()
    difficulty_filter = (request.args.get("difficulty") or "").strip()
    if search_term:
        active_query = active_query.filter(Worksheet.title.ilike(f"%{search_term}%"))
    if status_filter in {"draft", "published"}:
        active_query = active_query.filter(Worksheet.publication_status == status_filter)
    if difficulty_filter in {"easy", "medium", "hard"}:
        active_query = active_query.filter(Worksheet.difficulty_level == difficulty_filter)
    pagination = active_query.order_by(Worksheet.created_at.desc()).paginate(
        page=max(request.args.get("page", 1, type=int), 1), per_page=12, error_out=False
    )
    worksheets = pagination.items

    archived_worksheets = query.filter_by(
        is_archived=True,
    ).order_by(
        Worksheet.archived_at.desc()
    ).all()

    return render_template(
        "teacher_dashboard.html",
        worksheets=worksheets,
        archived_worksheets=archived_worksheets,
        pagination=pagination,
        search_term=search_term,
        status_filter=status_filter,
        difficulty_filter=difficulty_filter,
        total_count=total_count,
        published_count=published_count,
        draft_count=draft_count,
    )


@teacher_dashboard_bp.route(
    "/about/edit",
    methods=["GET", "POST"],
)
@teacher_required
def edit_about_page():
    """Allow the teacher to edit the public About page."""

    about_content = (
        AboutPage.get_or_create()
    )

    form = AboutPageForm(
        obj=about_content
    )

    if form.validate_on_submit():
        form.populate_obj(
            about_content
        )

        db.session.commit()

        flash(
            "تم تحديث صفحة من نحن بنجاح.",
            "success",
        )

        return redirect(
            url_for(
                "main.about"
            )
        )

    return render_template(
        "edit_about.html",
        form=form,
        about_content=about_content,
    )


@teacher_dashboard_bp.route(
    "/worksheets/upload",
    methods=["GET", "POST"],
)
@teacher_required
def upload_worksheet():
    """
    Upload a worksheet file and optionally an answer key.
    """

    form = UploadWorksheetForm()

    # ورقة العمل تعرض دروس أحدث فصل جرى تفعيله، وليس دروس الفصول القديمة.
    active_curricula_query = Curriculum.query.filter_by(
        is_active=True,
        processing_status="ready",
    )
    if current_user.role != "admin":
        active_curricula_query = active_curricula_query.filter(
            (Curriculum.created_by_id == current_user.id)
            | (Curriculum.created_by_id.is_(None))
        )
    latest_active_curriculum = active_curricula_query.order_by(
        Curriculum.activated_at.desc(),
        Curriculum.created_at.desc(),
        Curriculum.id.desc(),
    ).first()

    lessons = []
    active_semester = (
        latest_active_curriculum.semester
        if latest_active_curriculum is not None
        else None
    )
    if active_semester:
        lessons_query = Lesson.query.join(Unit).join(Curriculum).filter(
            Curriculum.is_active.is_(True),
            Curriculum.processing_status == "ready",
            Curriculum.semester == active_semester,
        )
        if current_user.role != "admin":
            lessons_query = lessons_query.filter(
                (Curriculum.created_by_id == current_user.id)
                | (Curriculum.created_by_id.is_(None))
            )
        lessons = lessons_query.order_by(
            Curriculum.subject,
            Curriculum.grade,
            Unit.order_index,
            Lesson.order_index,
        ).all()

    form.lesson_id.choices = [
        (0, "اختاري درسًا من الفصل النشط")
    ] + [
        (lesson.id, f"{lesson.unit.curriculum.subject} — {lesson.unit.title} — {lesson.title}")
        for lesson in lessons
    ]

    if form.validate_on_submit():
        worksheet = None
        saved_paths = []

        try:
            lesson_id = (
                form.lesson_id.data
                if form.lesson_id.data != 0
                else None
            )

            publication_status = (
                form.publication_status.data
                or "draft"
            )

            worksheet = Worksheet(
                lesson_id=lesson_id,
                created_by_id=current_user.id,
                title=form.title.data.strip(),
                description=(
                    form.description.data.strip()
                    if form.description.data
                    else None
                ),
                instructions=(
                    form.instructions.data.strip()
                    if form.instructions.data
                    else None
                ),
                difficulty_level=(
                    form.difficulty_level.data
                    or "medium"
                ),
                publication_status=(
                    publication_status
                ),
                creation_method="uploaded",
                allow_download=bool(
                    form.allow_download.data
                ),
                is_ai_generated=False,
                is_published=(
                    publication_status
                    == "published"
                ),
            )

            db.session.add(worksheet)
            db.session.flush()

            worksheet_file_data = (
                save_uploaded_file(
                    form.worksheet_file.data,
                    "worksheets",
                )
            )

            saved_paths.append(
                worksheet_file_data[
                    "storage_path"
                ]
            )

            worksheet_attachment = (
                WorksheetAttachment(
                    worksheet_id=worksheet.id,
                    attachment_type="worksheet",
                    **worksheet_file_data,
                )
            )

            db.session.add(
                worksheet_attachment
            )

            if (
                form.answer_key_file.data
                and form.answer_key_file.data.filename
            ):
                answer_key_data = (
                    save_uploaded_file(
                        form.answer_key_file.data,
                        "answer_keys",
                    )
                )

                saved_paths.append(
                    answer_key_data[
                        "storage_path"
                    ]
                )

                answer_key_attachment = (
                    WorksheetAttachment(
                        worksheet_id=worksheet.id,
                        attachment_type="answer_key",
                        **answer_key_data,
                    )
                )

                db.session.add(
                    answer_key_attachment
                )

            db.session.commit()

        except ValueError as error:
            db.session.rollback()
            flash(
                str(error),
                "error",
            )
            return render_template(
                "upload_worksheet.html",
                form=form,
            )

        except Exception as error:
            db.session.rollback()

            current_app.logger.exception(
                "Worksheet upload failed: %s",
                error,
            )

            upload_root = Path(
                current_app.config[
                    "UPLOAD_FOLDER"
                ]
            )

            for relative_path in saved_paths:
                file_path = (
                    upload_root
                    / relative_path
                )

                if file_path.exists():
                    file_path.unlink()

            flash(
                "حدث خطأ أثناء حفظ ورقة العمل.",
                "error",
            )

            return render_template(
                "upload_worksheet.html",
                form=form,
            )

        if (
            worksheet.publication_status
            == "published"
        ):
            flash(
                "تم رفع ورقة العمل ونشرها بنجاح.",
                "success",
            )
        else:
            flash(
                "تم حفظ ورقة العمل كمسودة بنجاح.",
                "success",
            )

        return redirect(
            url_for(
                "teacher_dashboard.dashboard"
            )
        )

    if request.method == "POST":
        for field_name, errors in form.errors.items():
            field = getattr(
                form,
                field_name,
                None,
            )

            label = (
                field.label.text
                if field is not None
                else field_name
            )

            for error in errors:
                flash(
                    f"{label}: {error}",
                    "error",
                )

    return render_template(
        "upload_worksheet.html",
        form=form,
    )


@teacher_dashboard_bp.route(
    "/worksheets/<int:worksheet_id>/edit",
    methods=["GET", "POST"],
)
@teacher_required
def edit_worksheet(worksheet_id):
    """
    Edit worksheet information and publication status.
    """

    worksheet = (
        get_teacher_worksheet_or_404(
            worksheet_id
        )
    )

    form = EditWorksheetForm(
        obj=worksheet
    )

    lessons = Lesson.query.order_by(
        Lesson.id
    ).all()

    form.lesson_id.choices = [
        (0, "بدون ربط بدرس محدد")
    ] + [
        (lesson.id, lesson.title)
        for lesson in lessons
    ]

    if request.method == "GET":
        form.lesson_id.data = (
            worksheet.lesson_id or 0
        )
        form.publication_status.data = (
            worksheet.publication_status
        )
        form.allow_download.data = (
            worksheet.allow_download
        )

    if form.validate_on_submit():
        worksheet.lesson_id = (
            form.lesson_id.data
            if form.lesson_id.data != 0
            else None
        )

        worksheet.title = (
            form.title.data.strip()
        )

        worksheet.description = (
            form.description.data.strip()
            if form.description.data
            else None
        )

        worksheet.instructions = (
            form.instructions.data.strip()
            if form.instructions.data
            else None
        )

        worksheet.difficulty_level = (
            form.difficulty_level.data
        )

        worksheet.publication_status = (
            form.publication_status.data
        )

        worksheet.is_published = (
            form.publication_status.data
            == "published"
        )

        worksheet.allow_download = bool(
            form.allow_download.data
        )

        db.session.commit()

        flash(
            "تم تحديث ورقة العمل بنجاح.",
            "success",
        )

        return redirect(
            url_for(
                "teacher_dashboard.dashboard"
            )
        )

    attachments = (
        WorksheetAttachment.query
        .filter_by(
            worksheet_id=worksheet.id
        )
        .order_by(
            WorksheetAttachment.created_at
        )
        .all()
    )

    return render_template(
        "edit_worksheet.html",
        form=form,
        worksheet=worksheet,
        attachments=attachments,
    )


@teacher_dashboard_bp.post(
    "/worksheets/<int:worksheet_id>/toggle-publish"
)
@teacher_required
def toggle_publish(worksheet_id):
    """
    Publish a draft worksheet or return a published
    worksheet to draft status.
    """

    worksheet = (
        get_teacher_worksheet_or_404(
            worksheet_id
        )
    )

    if (
        worksheet.publication_status
        == "published"
    ):
        worksheet.publication_status = (
            "draft"
        )
        worksheet.is_published = False

        message = (
            "تم تحويل ورقة العمل إلى مسودة."
        )

    else:
        worksheet.publication_status = (
            "published"
        )
        worksheet.is_published = True

        message = (
            "تم نشر ورقة العمل بنجاح."
        )

    db.session.commit()

    flash(
        message,
        "success",
    )

    return redirect(
        url_for(
            "teacher_dashboard.dashboard"
        )
    )


@teacher_dashboard_bp.post(
    "/worksheets/<int:worksheet_id>/archive"
)
@teacher_required
def archive_worksheet(worksheet_id):
    """Hide a worksheet without destroying attempts or results."""
    worksheet = get_teacher_worksheet_or_404(worksheet_id)
    worksheet.is_archived = True
    worksheet.archived_at = datetime.now(timezone.utc)
    worksheet.publication_status = "draft"
    worksheet.is_published = False
    db.session.commit()
    flash("تمت أرشفة ورقة العمل مع الاحتفاظ بنتائج الطلاب.", "success")
    return redirect(url_for("teacher_dashboard.dashboard"))


@teacher_dashboard_bp.post(
    "/worksheets/<int:worksheet_id>/restore"
)
@teacher_required
def restore_worksheet(worksheet_id):
    """Return an archived worksheet to the teacher workspace as a draft."""
    worksheet = get_teacher_worksheet_or_404(worksheet_id)
    worksheet.is_archived = False
    worksheet.archived_at = None
    worksheet.publication_status = "draft"
    worksheet.is_published = False
    db.session.commit()
    flash("تمت استعادة ورقة العمل كمسودة.", "success")
    return redirect(url_for("teacher_dashboard.dashboard"))


@teacher_dashboard_bp.post(
    "/worksheets/<int:worksheet_id>/delete"
)
@teacher_required
def delete_worksheet(worksheet_id):
    """Permanently delete only worksheets that have no student attempts."""
    worksheet = get_teacher_worksheet_or_404(worksheet_id)
    if worksheet.attempts:
        flash(
            "لا يمكن حذف ورقة مرتبطة بمحاولات طلاب. استخدمي الأرشفة لحفظ النتائج.",
            "error",
        )
        return redirect(url_for("teacher_dashboard.dashboard"))

    upload_root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    attachment_paths = []
    for attachment in worksheet.attachments:
        candidate = (upload_root / attachment.storage_path).resolve()
        if candidate.is_relative_to(upload_root):
            attachment_paths.append(candidate)

    db.session.delete(worksheet)
    db.session.commit()

    for candidate in attachment_paths:
        try:
            candidate.unlink(missing_ok=True)
        except OSError:
            current_app.logger.warning(
                "Could not remove worksheet attachment %s", candidate
            )

    flash("تم حذف ورقة العمل نهائيًا.", "success")
    return redirect(url_for("teacher_dashboard.dashboard"))
