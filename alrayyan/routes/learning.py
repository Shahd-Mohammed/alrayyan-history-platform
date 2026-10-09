from pathlib import Path

import re
from difflib import SequenceMatcher

from flask import Blueprint, abort, current_app, jsonify, render_template, request, send_file
from flask_login import current_user, login_required

from alrayyan.extensions import db
from alrayyan.models import CharacterAttempt, ConceptMap, Curriculum, HistoricalCharacter, HonorBoardEntry, LearningResource, Lesson, Unit, User, XPTransaction


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
    active_lessons = db.session.query(Lesson.id).join(Unit).join(Curriculum).filter(Curriculum.is_active.is_(True))
    return render_template(
        "learning/library.html",
        resources=LearningResource.query.filter(LearningResource.publication_status == "published", LearningResource.lesson_id.in_(active_lessons)).order_by(LearningResource.created_at.desc()).all(),
        maps=ConceptMap.query.filter(ConceptMap.publication_status == "published", ConceptMap.lesson_id.in_(active_lessons)).order_by(ConceptMap.created_at.desc()).all(),
        characters=HistoricalCharacter.query.filter(HistoricalCharacter.publication_status == "published", HistoricalCharacter.lesson_id.in_(active_lessons)).order_by(HistoricalCharacter.created_at.desc()).all(),
        honor_entries=HonorBoardEntry.query.filter_by(is_active=True).order_by(HonorBoardEntry.created_at.desc()).limit(8).all(),
    )


@learning_bp.get("/maps/<int:map_id>")
@login_required
def concept_map(map_id):
    row = db.session.get(ConceptMap, map_id)
    if row is None:
        abort(404)
    if row.publication_status != "published" and current_user.role not in {"teacher", "admin"}:
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
    upload_root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    target = (upload_root / (row.stored_path or "")).resolve()
    if not target.is_relative_to(upload_root) or not target.is_file():
        abort(404)
    return send_file(target, as_attachment=False, download_name=row.original_filename)


@learning_bp.get("/characters")
@login_required
def characters():
    active_lessons = db.session.query(Lesson.id).join(Unit).join(Curriculum).filter(Curriculum.is_active.is_(True))
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
    if not row.allow_download:
        abort(403)
    upload_root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    target = (upload_root / row.stored_path).resolve()
    if not target.is_relative_to(upload_root) or not target.is_file():
        abort(404)
    award_content_interaction(current_user, "resource_downloaded", "learning_resource", row.id)
    db.session.commit()
    return send_file(target, as_attachment=True, download_name=row.original_filename)
