from pathlib import Path
from datetime import datetime, timedelta, timezone
from html import escape as html_escape
from io import BytesIO

import re
from difflib import SequenceMatcher

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required

from alrayyan.extensions import db
from alrayyan.services.file_storage import resolve_stored_file
from alrayyan.models import CharacterAttempt, ConceptMap, Curriculum, DateReview, HistoricalCharacter, HistoricalDate, HonorBoardEntry, LearningResource, Lesson, Unit, User, XPTransaction
from alrayyan.services.learning_content_ai import generate_historical_date_drafts
from alrayyan.services.grade_access import lessons_for_user, student_can_access_lesson


learning_bp = Blueprint("learning", __name__, url_prefix="/learn")

def award_content_interaction(student, reason, source_type, source_id, amount=2):
    """Award a one-time, auditable reward for a meaningful learning action."""
    if student.role != "student":
        return 0
    existing = XPTransaction.query.filter_by(
        student_id=student.id,
        reason=reason,
        source_type=source_type,
        source_id=source_id,
    ).first()
    if existing:
        return 0
    db.session.add(XPTransaction(
        student_id=student.id,
        amount=amount,
        reason=reason,
        source_type=source_type,
        source_id=source_id,
    ))
    student.points = (student.points or 0) + amount
    student.level = max(1, student.points // 500 + 1)
    return amount



@learning_bp.get("/")
@login_required
def library():
    # Award a one-time reward for reaching the learning library; repeat refreshes do not farm points.
    if current_user.role == "student":
        award_content_interaction(
            current_user, "learning_library_opened", "student", current_user.id, amount=2
        )
        db.session.commit()
    active_lessons = lessons_for_user(current_user, active_only=True)
    return render_template(
        "learning/library.html",
        resources=LearningResource.query.filter(LearningResource.publication_status == "published", LearningResource.lesson_id.in_(active_lessons)).order_by(LearningResource.created_at.desc()).limit(6).all(),
        maps=ConceptMap.query.filter(ConceptMap.publication_status == "published", ConceptMap.lesson_id.in_(active_lessons)).order_by(ConceptMap.created_at.desc()).limit(6).all(),
        characters=HistoricalCharacter.query.filter(HistoricalCharacter.publication_status == "published", HistoricalCharacter.lesson_id.in_(active_lessons)).order_by(HistoricalCharacter.created_at.desc()).all(),
        honor_entries=HonorBoardEntry.query.filter_by(is_active=True).order_by(HonorBoardEntry.created_at.desc()).limit(8).all(),
    )


@learning_bp.get("/maps")
@login_required
def maps_archive():
    """Show published concept maps in a paginated archive."""
    active_lessons = lessons_for_user(current_user, active_only=True)
    pagination = ConceptMap.query.filter(
        ConceptMap.publication_status == "published",
        ConceptMap.lesson_id.in_(active_lessons),
    ).order_by(ConceptMap.created_at.desc()).paginate(
        page=max(request.args.get("page", 1, type=int), 1),
        per_page=12,
        error_out=False,
    )
    return render_template(
        "learning/archive.html",
        archive_kind="maps",
        pagination=pagination,
        rows=pagination.items,
    )


@learning_bp.get("/resources")
@login_required
def resources_archive():
    """Show published lesson summaries and supporting files in a paginated archive."""
    active_lessons = lessons_for_user(current_user, active_only=True)
    pagination = LearningResource.query.filter(
        LearningResource.publication_status == "published",
        LearningResource.lesson_id.in_(active_lessons),
    ).order_by(LearningResource.created_at.desc()).paginate(
        page=max(request.args.get("page", 1, type=int), 1),
        per_page=12,
        error_out=False,
    )
    return render_template(
        "learning/archive.html",
        archive_kind="resources",
        pagination=pagination,
        rows=pagination.items,
    )


@learning_bp.get("/maps/<int:map_id>")
@login_required
def concept_map(map_id):
    row = db.session.get(ConceptMap, map_id)
    if row is None:
        abort(404)
    if row.publication_status != "published" and current_user.role not in {"teacher", "admin"}:
        abort(404)
    if not student_can_access_lesson(current_user, row.lesson):
        abort(404)
    award_content_interaction(current_user, "concept_map_viewed", "concept_map", row.id)
    db.session.commit()
    return render_template("learning/concept_map.html", concept_map=row)


@learning_bp.get("/maps/<int:map_id>/file")
@login_required
def concept_map_file(map_id):
    row = ConceptMap.query.filter_by(id=map_id, creation_method="upload").first_or_404()
    if row.publication_status != "published" and current_user.role not in {"teacher", "admin"}:
        abort(404)
    if not student_can_access_lesson(current_user, row.lesson):
        abort(404)
    try:
        target = resolve_stored_file(row.stored_path)
    except ValueError:
        current_app.logger.warning(
            "Blocked concept-map file path for map %s",
            row.id,
        )
        abort(403)
    if target is None:
        current_app.logger.error(
            "Concept-map file is missing from local and durable storage: map=%s path=%s",
            row.id,
            row.stored_path,
        )
        abort(404)
    return send_file(
        target,
        as_attachment=False,
        download_name=Path(row.original_filename or f"concept-map-{row.id}").name,
        mimetype=row.mime_type or "application/octet-stream",
    )


def build_concept_map_svg(concept_map):
    """Render a downloadable SVG for a generated concept map."""
    nodes = list(concept_map.nodes)
    node_width = 270
    node_height = 100
    margin = 50
    gap_y = 45

    raw_positions = [
        (float(node.position_x or 0), float(node.position_y or 0))
        for node in nodes
    ]
    if raw_positions and all(position == (0.0, 0.0) for position in raw_positions):
        raw_positions = [
            (0.0, index * (node_height + gap_y))
            for index in range(len(nodes))
        ]

    positions = {}
    for node, (x, y) in zip(nodes, raw_positions):
        positions[node.id] = (x, y)

    if positions:
        min_x = min(x for x, _ in positions.values())
        min_y = min(y for _, y in positions.values())
        max_x = max(x for x, _ in positions.values())
        max_y = max(y for _, y in positions.values())
    else:
        min_x = min_y = max_x = max_y = 0.0

    normalized = {
        node_id: (
            x - min_x + margin,
            y - min_y + margin,
        )
        for node_id, (x, y) in positions.items()
    }
    width = max(2 * margin + node_width, max_x - min_x + node_width + 2 * margin)
    height = max(2 * margin + node_height, max_y - min_y + node_height + 2 * margin)

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{int(width)}" height="{int(height)}" viewBox="0 0 {int(width)} {int(height)}">',
        '<rect width="100%" height="100%" fill="#f8f6f1"/>',
        f'<text x="{width / 2:.1f}" y="30" text-anchor="middle" font-size="22" font-family="Arial, sans-serif" fill="#17243b" direction="rtl">{html_escape(concept_map.title or "خريطة مفاهيمية")}</text>',
    ]

    for edge in concept_map.edges:
        if edge.source_node_id not in normalized or edge.target_node_id not in normalized:
            continue
        sx, sy = normalized[edge.source_node_id]
        tx, ty = normalized[edge.target_node_id]
        x1 = sx + node_width / 2
        y1 = sy + node_height / 2
        x2 = tx + node_width / 2
        y2 = ty + node_height / 2
        parts.append(
            f'<path d="M {x1:.1f} {y1:.1f} C {(x1+x2)/2:.1f} {y1:.1f}, '
            f'{(x1+x2)/2:.1f} {y2:.1f}, {x2:.1f} {y2:.1f}" '
            'fill="none" stroke="#b38a3e" stroke-width="3"/>'
        )
        label = html_escape((edge.label or "").strip())
        if label:
            parts.append(
                f'<text x="{(x1+x2)/2:.1f}" y="{(y1+y2)/2-7:.1f}" '
                'text-anchor="middle" font-size="13" font-family="Arial, sans-serif" '
                f'fill="#5d6470" direction="rtl">{label}</text>'
            )

    for node in nodes:
        x, y = normalized[node.id]
        title = html_escape(node.label or "")
        description = html_escape((node.description or "").strip())
        if len(description) > 42:
            description = html_escape((node.description or "").strip()[:39] + "…")
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{node_width}" height="{node_height}" '
            'rx="15" fill="#ffffff" stroke="#b38a3e" stroke-width="2"/>'
        )
        parts.append(
            f'<text x="{x + node_width / 2:.1f}" y="{y + 38:.1f}" text-anchor="middle" '
            'font-size="18" font-weight="700" font-family="Arial, sans-serif" '
            f'fill="#17243b" direction="rtl">{title}</text>'
        )
        if description:
            parts.append(
                f'<text x="{x + node_width / 2:.1f}" y="{y + 68:.1f}" text-anchor="middle" '
                'font-size="13" font-family="Arial, sans-serif" '
                f'fill="#5d6470" direction="rtl">{description}</text>'
            )

    parts.append("</svg>")
    return "\n".join(parts)


@learning_bp.get("/maps/<int:map_id>/download")
@login_required
def download_concept_map(map_id):
    """Download an uploaded map or export an interactive map as SVG."""
    row = db.session.get(ConceptMap, map_id)
    if row is None:
        abort(404)
    if row.publication_status != "published" and current_user.role not in {"teacher", "admin"}:
        abort(404)
    if not student_can_access_lesson(current_user, row.lesson):
        abort(404)

    filename_stem = Path(row.title or f"concept-map-{row.id}").name.strip()
    if row.creation_method == "upload":
        try:
            target = resolve_stored_file(row.stored_path)
        except ValueError:
            current_app.logger.warning(
                "Blocked concept-map download path for map %s",
                row.id,
            )
            abort(403)
        if target is None:
            current_app.logger.error(
                "Concept-map download file is missing from local and durable storage: map=%s path=%s",
                row.id,
                row.stored_path,
            )
            abort(404)
        original_name = Path(row.original_filename or filename_stem)
        return send_file(
            target,
            as_attachment=True,
            download_name=original_name.name,
            mimetype=row.mime_type or "application/octet-stream",
        )

    svg_content = build_concept_map_svg(row)
    return send_file(
        BytesIO(svg_content.encode("utf-8")),
        as_attachment=True,
        download_name=f"{filename_stem}.svg",
        mimetype="image/svg+xml; charset=utf-8",
    )


@learning_bp.get("/characters")
@login_required
def characters():
    active_lessons = lessons_for_user(current_user, active_only=True)
    rows = HistoricalCharacter.query.filter(HistoricalCharacter.publication_status == "published", HistoricalCharacter.lesson_id.in_(active_lessons)).order_by(HistoricalCharacter.name).all()
    return render_template("learning/characters.html", characters=rows)


@learning_bp.get("/honor-board")
@login_required
def honor_board():
    entries = HonorBoardEntry.query.filter_by(is_active=True).order_by(HonorBoardEntry.created_at.desc()).limit(30).all()
    automatic = User.query.filter_by(role="student", is_active_account=True).filter(User.points > 0).order_by(User.points.desc(), User.full_name).limit(6).all()
    return render_template("learning/honor_board.html", entries=entries, automatic=automatic)


def normalize_answer(value):
    value = re.sub(r"[\W_]+", " ", (value or "").casefold(), flags=re.UNICODE)
    return " ".join(value.split())


@learning_bp.post("/characters/<int:character_id>/answer")
@login_required
def answer_character(character_id):
    if current_user.role != "student":
        abort(403)
    row = HistoricalCharacter.query.filter_by(id=character_id, publication_status="published").first_or_404()
    if not student_can_access_lesson(current_user, row.lesson):
        abort(404)
    payload = request.get_json(silent=True) or {}
    answer = str(payload.get("answer") or "").strip()[:250]
    if not answer:
        return jsonify(success=False, error="اكتبي اسم الشخصية أولًا."), 400
    existing = CharacterAttempt.query.filter_by(character_id=row.id, student_id=current_user.id).first()
    expected, actual = normalize_answer(row.name), normalize_answer(answer)
    correct = expected == actual or SequenceMatcher(None, expected, actual).ratio() >= 0.82
    hints_used = min(max(int(payload.get("hints_used") or 0), 0), 3)
    already_rewarded = bool(existing and (existing.xp_awarded or 0) > 0)
    xp = (15 if hints_used == 0 else 10 if hints_used == 1 else 6) if correct and not already_rewarded else 0
    if existing is None:
        existing = CharacterAttempt(character_id=row.id, student_id=current_user.id, answer_text=answer, is_correct=correct, hints_used=hints_used, xp_awarded=xp)
        db.session.add(existing)
        if xp:
            db.session.add(XPTransaction(student_id=current_user.id, amount=xp, reason="character_identified", source_type="historical_character", source_id=row.id))
            current_user.points = (current_user.points or 0) + xp
    else:
        existing.answer_text = answer
        existing.is_correct = existing.is_correct or correct
        existing.hints_used = min(existing.hints_used, hints_used)
        if xp:
            existing.xp_awarded = xp
            db.session.add(XPTransaction(student_id=current_user.id, amount=xp, reason="character_identified", source_type="historical_character", source_id=row.id))
            current_user.points = (current_user.points or 0) + xp
    current_user.level = max(1, (current_user.points or 0) // 500 + 1)
    db.session.commit()
    return jsonify(success=True, correct=correct, xp_awarded=xp, answer=row.name if correct else None, feedback=("إجابة موفقة! ربطتِ التلميحات بالشخصية الصحيحة." if correct else "محاولة حلوة. راجعي التلميحات وجرّبي مرة أخرى دون كشف الإجابة."))


@learning_bp.get("/resources/<int:resource_id>/download")
@login_required
def download_resource(resource_id):
    row = LearningResource.query.filter_by(id=resource_id, publication_status="published").first_or_404()
    if not student_can_access_lesson(current_user, row.lesson):
        abort(404)
    if not row.allow_download:
        abort(403)
    try:
        target = resolve_stored_file(row.stored_path)
    except ValueError:
        current_app.logger.warning(
            "Blocked learning-resource path for resource %s",
            row.id,
        )
        abort(403)
    if target is None:
        current_app.logger.error(
            "Learning-resource file is missing from local and durable storage: resource=%s path=%s",
            row.id,
            row.stored_path,
        )
        abort(404)
    award_content_interaction(current_user, "resource_downloaded", "learning_resource", row.id)
    db.session.commit()
    return send_file(
        target,
        as_attachment=True,
        download_name=Path(row.original_filename or f"learning-resource-{row.id}").name,
        mimetype=row.mime_type or "application/octet-stream",
    )



@learning_bp.get("/dates")
@login_required
def date_memory():
    """Student-only spaced practice with self-generated AI cards from active lessons."""
    if current_user.role != "student":
        abort(403)

    visible_lesson_ids = lessons_for_user(current_user, active_only=True)
    lessons = (
        Lesson.query
        .join(Unit)
        .join(Curriculum)
        .filter(
            Curriculum.is_active.is_(True),
            Curriculum.processing_status == "ready",
            Lesson.is_published.is_(True),
            Lesson.id.in_(visible_lesson_ids or [-1]),
        )
        .order_by(Curriculum.subject, Unit.order_index, Lesson.order_index)
        .all()
    )
    active_lesson_ids = [lesson.id for lesson in lessons]
    dates = (
        HistoricalDate.query
        .filter(
            HistoricalDate.is_published.is_(True),
            HistoricalDate.lesson_id.in_(active_lesson_ids or [-1]),
        )
        .order_by(HistoricalDate.sort_year.asc(), HistoricalDate.id.asc())
        .all()
    )
    date_ids = [item.id for item in dates]
    reviews = {}
    if date_ids:
        reviews = {
            item.historical_date_id: item
            for item in DateReview.query.filter(
                DateReview.student_id == current_user.id,
                DateReview.historical_date_id.in_(date_ids),
            ).all()
        }
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    due_count = sum(1 for item in dates if item.id not in reviews or reviews[item.id].next_review_at <= now)
    return render_template("learning/date_memory.html", dates=dates, reviews=reviews, due_count=due_count, now=now, lessons=lessons)


@learning_bp.post("/dates/generate")
@login_required
def generate_student_date_memory():
    """Let students generate their own lesson-grounded date-memory cards with AI."""
    if current_user.role != "student":
        abort(403)
    lesson_id = request.form.get("lesson_id", type=int)
    lesson = (
        Lesson.query
        .join(Unit)
        .join(Curriculum)
        .filter(
            Lesson.id == lesson_id,
            Curriculum.is_active.is_(True),
            Curriculum.processing_status == "ready",
            Lesson.is_published.is_(True),
            Lesson.id.in_(lessons_for_user(current_user, active_only=True) or [-1]),
        )
        .first_or_404()
    )
    existing_published = HistoricalDate.query.filter_by(
        lesson_id=lesson.id,
        is_published=True,
    ).count()
    if existing_published:
        flash("هذا الدرس لديه بطاقات مراجعة جاهزة بالفعل. ابدئي المراجعة أو اختاري درسًا آخر لإنشاء بطاقات جديدة.", "info")
        return redirect(url_for("learning.date_memory"))

    try:
        generated = generate_historical_date_drafts(lesson)
        existing = HistoricalDate.query.filter_by(lesson_id=lesson.id, is_published=True).all()
        existing_keys = {
            (normalize_answer(item.date_label), normalize_answer(item.event_title))
            for item in existing
        }
        created_count = 0
        for item in generated:
            key = (normalize_answer(item["date_label"]), normalize_answer(item["event_title"]))
            if key in existing_keys:
                continue
            db.session.add(HistoricalDate(
                lesson_id=lesson.id,
                date_label=item["date_label"],
                sort_year=item["sort_year"],
                event_title=item["event_title"],
                event_description=item["event_description"],
                memory_hint=item["memory_hint"],
                importance_level=1,
                is_published=True,
            ))
            existing_keys.add(key)
            created_count += 1
        if not created_count:
            raise RuntimeError("توجد بطاقات مشابهة لهذا الدرس بالفعل. اختاري درسًا آخر أو ابدئي المراجعة.")
        db.session.commit()
        flash(f"أنشأ الذكاء الاصطناعي {created_count} بطاقات مراجعة من درس «{lesson.title}». أصبحت جاهزة لكِ.", "success")
    except Exception as error:
        db.session.rollback()
        current_app.logger.exception("Student date-memory generation failed")
        flash(str(error) if isinstance(error, RuntimeError) else "تعذر إنشاء البطاقات الآن. حاولي مرة أخرى بعد قليل.", "error")
    return redirect(url_for("learning.date_memory"))


@learning_bp.post("/dates/<int:date_id>/review")
@login_required
def review_historical_date(date_id):
    """Check recall, schedule the next review, and award a single small mastery reward."""
    if current_user.role != "student":
        abort(403)

    row = HistoricalDate.query.filter_by(id=date_id, is_published=True).first_or_404()
    if not student_can_access_lesson(current_user, row.lesson):
        abort(404)
    answer = (request.form.get("answer") or "").strip()[:300]
    if not answer:
        flash("اكتبي الحدث المرتبط بالتاريخ أولًا.", "error")
        return redirect(url_for("learning.date_memory"))

    expected = normalize_answer(row.event_title)
    actual = normalize_answer(answer)
    is_correct = expected == actual or SequenceMatcher(None, expected, actual).ratio() >= 0.82
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    review = DateReview.query.filter_by(historical_date_id=row.id, student_id=current_user.id).first()
    if review is None:
        review = DateReview(historical_date_id=row.id, student_id=current_user.id, repetitions=0, interval_days=0, easiness_factor=2.5, next_review_at=now)
        db.session.add(review)

    if is_correct:
        review.repetitions = (review.repetitions or 0) + 1
        if review.repetitions == 1:
            interval = 1
        elif review.repetitions == 2:
            interval = 3
        elif review.repetitions == 3:
            interval = 7
        else:
            interval = max(1, round((review.interval_days or 7) * (review.easiness_factor or 2.5)))
        review.easiness_factor = min(3.0, (review.easiness_factor or 2.5) + 0.05)
    else:
        review.repetitions = 0
        interval = 1
        review.easiness_factor = max(1.3, (review.easiness_factor or 2.5) - 0.2)

    review.interval_days = interval
    review.last_result = 5 if is_correct else 2
    review.last_reviewed_at = now
    review.next_review_at = now + timedelta(days=interval)

    xp_awarded = 0
    if is_correct:
        existing = XPTransaction.query.filter_by(student_id=current_user.id, reason="historical_date_recalled", source_type="historical_date", source_id=row.id).first()
        if existing is None:
            xp_awarded = 3
            db.session.add(XPTransaction(student_id=current_user.id, amount=xp_awarded, reason="historical_date_recalled", source_type="historical_date", source_id=row.id))
            current_user.points = (current_user.points or 0) + xp_awarded
            current_user.level = max(1, current_user.points // 500 + 1)

    db.session.commit()
    if is_correct:
        message = f"إجابة صحيحة! الحدث هو: {row.event_title}. موعد المراجعة التالية بعد {interval} يومًا."
        if xp_awarded:
            message += " حصلتِ على 3 نقاط لأول تذكّر صحيح لهذا التاريخ."
        flash(message, "success")
    else:
        flash(f"راجعي الربط مرة أخرى: {row.date_label} يرتبط بحدث «{row.event_title}». سنعيد عرضه غدًا.", "warning")
    return redirect(url_for("learning.date_memory"))
