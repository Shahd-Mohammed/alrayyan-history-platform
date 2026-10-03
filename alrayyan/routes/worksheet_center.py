from functools import wraps

from flask import Blueprint, abort, render_template, request
from flask_login import current_user, login_required

from alrayyan.models import Worksheet


worksheet_center_bp = Blueprint(
    "worksheet_center",
    __name__,
    url_prefix="/teacher-dashboard/worksheets",
)


def teacher_required(view_function):
    @wraps(view_function)
    @login_required
    def wrapped(*args, **kwargs):
        if current_user.role not in {"teacher", "admin"}:
            abort(403)
        return view_function(*args, **kwargs)

    return wrapped


@worksheet_center_bp.get("")
@teacher_required
def center():
    query = Worksheet.query

    if current_user.role != "admin":
        query = query.filter_by(created_by_id=current_user.id)

    active_query = query.filter_by(is_archived=False)

    total_count = active_query.count()
    published_count = active_query.filter(
        Worksheet.publication_status == "published"
    ).count()
    draft_count = active_query.filter(
        Worksheet.publication_status == "draft"
    ).count()

    search_term = (request.args.get("q") or "").strip()
    status_filter = (request.args.get("status") or "").strip()
    difficulty_filter = (request.args.get("difficulty") or "").strip()

    if search_term:
        active_query = active_query.filter(
            Worksheet.title.ilike(f"%{search_term}%")
        )

    if status_filter in {"draft", "published"}:
        active_query = active_query.filter(
            Worksheet.publication_status == status_filter
        )

    if difficulty_filter in {"easy", "medium", "hard"}:
        active_query = active_query.filter(
            Worksheet.difficulty_level == difficulty_filter
        )

    pagination = active_query.order_by(
        Worksheet.created_at.desc()
    ).paginate(
        page=max(request.args.get("page", 1, type=int), 1),
        per_page=12,
        error_out=False,
    )

    archived_worksheets = query.filter_by(
        is_archived=True,
    ).order_by(
        Worksheet.archived_at.desc()
    ).all()

    return render_template(
        "worksheet_center.html",
        worksheets=pagination.items,
        archived_worksheets=archived_worksheets,
        pagination=pagination,
        search_term=search_term,
        status_filter=status_filter,
        difficulty_filter=difficulty_filter,
        total_count=total_count,
        published_count=published_count,
        draft_count=draft_count,
    )
