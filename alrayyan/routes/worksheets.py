from pathlib import Path
from urllib.parse import quote

from flask import (
    Blueprint,
    abort,
    current_app,
    render_template,
    send_file,
)
from flask_login import (
    current_user,
    login_required,
)

from alrayyan.models import (
    Worksheet,
    WorksheetAttachment,
    WorksheetAttempt,
)


worksheets_bp = Blueprint(
    "worksheets",
    __name__,
    url_prefix="/worksheets",
)


@worksheets_bp.get("/")
@login_required
def worksheet_list():
    """
    Display published worksheets only.
    """

    worksheets = (
        Worksheet.query
        .filter_by(
            publication_status="published",
            is_published=True,
        )
        .order_by(
            Worksheet.created_at.desc()
        )
        .all()
    )

    return render_template(
        "worksheets.html",
        worksheets=worksheets,
    )


@worksheets_bp.get(
    "/<int:worksheet_id>"
)
@login_required
def worksheet_details(worksheet_id):
    """
    Display one published worksheet.
    """

    worksheet = (
        Worksheet.query
        .filter_by(
            id=worksheet_id,
            publication_status="published",
            is_published=True,
        )
        .first_or_404()
    )

    worksheet_file = (
        WorksheetAttachment.query
        .filter_by(
            worksheet_id=worksheet.id,
            attachment_type="worksheet",
        )
        .first()
    )

    max_attempts = worksheet.max_attempts or 1
    attempts_used = 0
    attempts_remaining = max_attempts
    open_attempt = None

    if (
        current_user.is_authenticated
        and current_user.role == "student"
    ):
        open_attempt = (
            WorksheetAttempt.query
            .filter_by(
                worksheet_id=worksheet.id,
                student_id=current_user.id,
                submitted_at=None,
            )
            .order_by(
                WorksheetAttempt.started_at.desc()
            )
            .first()
        )

        completed_attempts = (
            WorksheetAttempt.query
            .filter_by(
                worksheet_id=worksheet.id,
                student_id=current_user.id,
            )
            .filter(
                WorksheetAttempt.submitted_at.isnot(None)
            )
            .count()
        )

        attempts_used = (
            completed_attempts
            + (1 if open_attempt else 0)
        )

        attempts_remaining = max(
            max_attempts - attempts_used,
            0,
        )

    return render_template(
        "worksheet_details.html",
        worksheet=worksheet,
        worksheet_file=worksheet_file,
        max_attempts=max_attempts,
        attempts_used=attempts_used,
        attempts_remaining=attempts_remaining,
        open_attempt=open_attempt,
    )

@worksheets_bp.get(
    "/<int:worksheet_id>/download"
)
@login_required
def download_worksheet(worksheet_id):
    """
    Force the browser to download a published
    worksheet without opening its PDF viewer.
    """

    worksheet = (
        Worksheet.query
        .filter_by(
            id=worksheet_id,
            publication_status="published",
            is_published=True,
        )
        .first_or_404()
    )

    if not worksheet.allow_download:
        abort(403)

    attachment = (
        WorksheetAttachment.query
        .filter_by(
            worksheet_id=worksheet.id,
            attachment_type="worksheet",
        )
        .first_or_404()
    )

    upload_root = Path(
        current_app.config["UPLOAD_FOLDER"]
    ).resolve()

    stored_path = Path(
        attachment.storage_path
    )

    if stored_path.is_absolute():
        file_path = stored_path.resolve()
    else:
        file_path = (
            upload_root / stored_path
        ).resolve()

    try:
        file_path.relative_to(
            upload_root
        )
    except ValueError:
        current_app.logger.warning(
            "Blocked worksheet path: %s",
            file_path,
        )
        abort(403)

    if not file_path.is_file():
        current_app.logger.error(
            "Worksheet file was not found: %s",
            file_path,
        )
        abort(404)

    original_name = Path(
        attachment.original_filename
    )

    clean_stem = original_name.stem.strip()

    clean_suffix = (
        original_name.suffix.lower()
        or file_path.suffix.lower()
        or ".pdf"
    )

    arabic_filename = (
        f"{clean_stem}{clean_suffix}"
    )

    encoded_filename = quote(
        arabic_filename
    )

    fallback_filename = (
        f"worksheet-{worksheet.id}"
        f"{clean_suffix}"
    )

    response = send_file(
        path_or_file=str(file_path),
        mimetype="application/octet-stream",
        as_attachment=True,
        download_name=fallback_filename,
        conditional=False,
        etag=False,
        max_age=0,
    )

    response.headers[
        "Content-Type"
    ] = "application/octet-stream"

    response.headers[
        "Content-Disposition"
    ] = (
        "attachment; "
        f'filename="{fallback_filename}"; '
        f"filename*=UTF-8''{encoded_filename}"
    )

    response.headers[
        "Cache-Control"
    ] = "no-store, no-cache, must-revalidate"

    response.headers[
        "Pragma"
    ] = "no-cache"

    return response