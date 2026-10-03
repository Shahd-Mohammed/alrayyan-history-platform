from datetime import datetime, timezone

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from alrayyan.extensions import db
from alrayyan.models import (
    ChallengeSession, ConceptMastery, ContentChunk, LearningPlanItem,
    Lesson, TutorConversation, TutorMessage, TutorMessageSource,
    XPTransaction,
)
from alrayyan.services.tutor_engine import tutor_reply


teacher_bp = Blueprint("teacher", __name__, url_prefix="/teacher")
@teacher_bp.before_request
def restrict_ai_tutor_to_students():
    """
    Restrict the interactive AI Tutor,
    learning plan, quizzes, and points
    wallet to student accounts.
    """

    if not current_user.is_authenticated:
        return None

    if current_user.role == "student":
        return None

    return redirect(
        url_for(
            "teacher_dashboard.dashboard"
        )
    )


def utc_now():
    return datetime.now(timezone.utc)


def get_owned_conversation_or_404(conversation_id):
    conversation = db.session.get(TutorConversation, conversation_id)
    if conversation is None:
        abort(404)
    if conversation.student_id != current_user.id:
        abort(403)
    return conversation


def serialize_sources(message):
    items, seen = [], set()
    for link in message.source_links:
        chunk, source = link.chunk, link.chunk.source
        key = (source.id, chunk.page_number, chunk.lesson_id)
        if key in seen:
            continue
        seen.add(key)
        items.append({
            "title": source.title,
            "lesson_title": chunk.lesson.title if chunk.lesson else None,
            "page_number": chunk.page_number,
            "is_primary": source.is_primary,
        })
    return items


def serialize_message(message):
    return {
        "id": message.id,
        "role": message.role,
        "content": message.content,
        "action": message.action,
        "evaluation": message.evaluation,
        "concept": message.concept,
        "mastery_delta": message.mastery_delta,
        "sources": serialize_sources(message),
    }


def update_mastery(conversation, payload):
    if not conversation.lesson_id or payload["evaluation"] == "not_evaluated":
        return None
    mastery = ConceptMastery.query.filter_by(
        student_id=current_user.id,
        lesson_id=conversation.lesson_id,
        concept=payload["concept"],
    ).first()
    if mastery is None:
        mastery = ConceptMastery(
            student_id=current_user.id,
            lesson_id=conversation.lesson_id,
            concept=payload["concept"],
            mastery_score=50,
            correct_count=0,
            partial_count=0,
            incorrect_count=0,
        )
        db.session.add(mastery)
    mastery.mastery_score = min(max(
        (mastery.mastery_score or 50) + payload["mastery_delta"], 0
    ), 100)
    if payload["evaluation"] == "correct":
        mastery.correct_count = (mastery.correct_count or 0) + 1
    elif payload["evaluation"] == "partially_correct":
        mastery.partial_count = (mastery.partial_count or 0) + 1
    elif payload["evaluation"] in {"incorrect", "needs_explanation"}:
        mastery.incorrect_count = (mastery.incorrect_count or 0) + 1
    mastery.last_reviewed_at = utc_now()
    return mastery


def refresh_learning_plan(student_id):
    weak_items = (
        ConceptMastery.query
        .filter(ConceptMastery.student_id == student_id, ConceptMastery.mastery_score < 70)
        .order_by(ConceptMastery.mastery_score.asc())
        .limit(5).all()
    )
    for mastery in weak_items:
        item_title = f"راجعي مفهوم: {mastery.concept}"
        existing = LearningPlanItem.query.filter_by(
            student_id=student_id,
            lesson_id=mastery.lesson_id,
            item_type="concept_review",
            title=item_title,
        ).order_by(LearningPlanItem.created_at.desc()).first()
        description = (
            f"درجة إتقانك الحالية {mastery.mastery_score}%. "
            "ابدئي بمحادثة قصيرة ثم اجتازي اختبار إتقان من خمس جولات."
        )
        if existing and existing.status == "pending":
            existing.description = description
            existing.priority = 100 - mastery.mastery_score
        elif (
            existing
            and existing.status == "completed"
            and existing.completed_at
            and mastery.last_reviewed_at <= existing.completed_at
        ):
            continue
        else:
            db.session.add(LearningPlanItem(
                student_id=student_id,
                lesson_id=mastery.lesson_id,
                item_type="concept_review",
                title=item_title,
                description=description,
                priority=100 - mastery.mastery_score,
            ))


@teacher_bp.get("/")
@login_required
def teacher_page():
    lessons = (
        Lesson.query.join(ContentChunk, ContentChunk.lesson_id == Lesson.id)
        .filter(ContentChunk.embedding.isnot(None)).distinct().order_by(Lesson.id).all()
    )
    conversations = (
        TutorConversation.query.filter_by(student_id=current_user.id)
        .order_by(TutorConversation.updated_at.desc()).limit(10).all()
    )
    raw_lesson_id = request.args.get("lesson_id", "")
    initial_lesson_id = int(raw_lesson_id) if raw_lesson_id.isdigit() else None
    initial_concept = (request.args.get("concept") or "").strip()[:250]
    review_mode = request.args.get("mode") == "review"
    return render_template(
        "teacher.html",
        lessons=lessons,
        conversations=conversations,
        initial_lesson_id=initial_lesson_id,
        initial_concept=initial_concept,
        review_mode=review_mode,
    )


@teacher_bp.post("/conversations")
@login_required
def create_conversation():
    data = request.get_json(silent=True) or {}
    raw_lesson_id = str(data.get("lesson_id") or "")
    lesson = db.session.get(Lesson, int(raw_lesson_id)) if raw_lesson_id.isdigit() else None
    initial_concept = str(data.get("concept") or "").strip()[:250] or None
    conversation = TutorConversation(
        student_id=current_user.id,
        lesson_id=lesson.id if lesson else None,
        title=f"مراجعة {lesson.title}" if lesson else "محادثة تعليمية جديدة",
        difficulty=data.get("difficulty", "adaptive"),
        current_concept=initial_concept,
    )
    db.session.add(conversation)
    db.session.flush()
    greeting = TutorMessage(
        conversation_id=conversation.id,
        role="tutor",
        action="ask_diagnostic",
        evaluation="not_evaluated",
        content=(
            (
                f"يا هلا {current_user.first_name} 🤍 خلينا ناخذها على راحتنا. "
                + (
                    f"اليوم نركز على «{initial_concept}» من درس «{lesson.title}»؟ احكيلي من وين بدك نبدأ."
                    if initial_concept
                    else f"درس «{lesson.title}» جاهز إلنا، بس مش لازم نبلش رسمي 😄 احكيلي شو حابة نفهم أو نحكي عنه."
                )
            )
            if lesson else
            f"يا هلا {current_user.first_name} 🤍 خذي راحتك، أنا معك. بدك ندرس، نسولف شوي، ولا نعملها بطريقة ألطف؟"
        ),
    )
    db.session.add(greeting)
    db.session.commit()
    return jsonify({
        "success": True,
        "conversation_id": conversation.id,
        "title": conversation.title,
        "lesson_id": conversation.lesson_id,
        "concept": conversation.current_concept,
        "messages": [serialize_message(greeting)],
    })


@teacher_bp.get("/conversations/<int:conversation_id>/messages")
@login_required
def conversation_messages(conversation_id):
    conversation = get_owned_conversation_or_404(conversation_id)
    return jsonify({
        "success": True,
        "conversation_id": conversation.id,
        "title": conversation.title,
        "lesson_id": conversation.lesson_id,
        "concept": conversation.current_concept,
        "messages": [serialize_message(item) for item in conversation.messages],
    })


@teacher_bp.post("/conversations/<int:conversation_id>/message")
@login_required
def send_tutor_message(conversation_id):
    conversation = get_owned_conversation_or_404(conversation_id)
    data = request.get_json(silent=True) or {}
    student_text = str(
        data.get("message")
        or data.get("question")
        or ""
    ).strip()
    try:
        student_message = TutorMessage(
            conversation_id=conversation.id, role="student", content=student_text
        )
        db.session.add(student_message)
        db.session.flush()
        payload = tutor_reply(conversation, student_text)
        tutor_message = TutorMessage(
            conversation_id=conversation.id,
            role="tutor",
            content=payload["reply"],
            action=payload["action"],
            evaluation=payload["evaluation"],
            concept=payload["concept"],
            mastery_delta=payload["mastery_delta"],
            model=payload["model"],
            prompt_version=payload["prompt_version"],
        )
        db.session.add(tutor_message)
        db.session.flush()
        valid_chunks = ContentChunk.query.filter(
            ContentChunk.id.in_(payload["source_chunk_ids"])
        ).all() if payload["source_chunk_ids"] else []
        for chunk in valid_chunks:
            db.session.add(TutorMessageSource(
                message_id=tutor_message.id, chunk_id=chunk.id
            ))
        conversation.current_concept = payload["concept"]
        conversation.tutor_state = payload["action"]
        conversation.updated_at = utc_now()
        if conversation.title == "محادثة تعليمية جديدة":
            conversation.title = student_text[:80]
        mastery = update_mastery(conversation, payload)
        xp_awarded = {
            "correct": 5,
            "partially_correct": 2,
        }.get(payload["evaluation"], 0)
        if xp_awarded:
            db.session.add(XPTransaction(
                student_id=current_user.id,
                amount=xp_awarded,
                reason="tutor_evaluated_answer",
                source_type="tutor_message",
                source_id=tutor_message.id,
            ))
            current_user.points = (current_user.points or 0) + xp_awarded
            current_user.level = max(1, current_user.points // 500 + 1)
        refresh_learning_plan(current_user.id)
        db.session.commit()
        return jsonify({
            "success": True,
            "message": serialize_message(tutor_message),
            "mastery_score": mastery.mastery_score if mastery else None,
            "progress_updated": mastery is not None,
            "xp_awarded": xp_awarded,
            "points_total": current_user.points,
            "learning_hub_url": url_for("teacher.learning_hub"),
            "suggest_quick_quiz": payload["suggest_quick_quiz"],
        })
    except ValueError as error:
        db.session.rollback()
        return jsonify({"success": False, "error": str(error)}), 400
    except RuntimeError as error:
        db.session.rollback()
        current_app.logger.exception("Interactive tutor request failed")
        return jsonify({"success": False, "error": str(error)}), 502
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Unexpected interactive tutor error")
        return jsonify({"success": False, "error": "حدث خطأ غير متوقع. حاولي مرة أخرى."}), 500


@teacher_bp.post("/quick-quiz/start")
@login_required
def start_quick_quiz():
    data = request.get_json(silent=True) or {}
    raw_lesson_id = str(data.get("lesson_id") or "")
    lesson = db.session.get(Lesson, int(raw_lesson_id)) if raw_lesson_id.isdigit() else None
    if lesson is None:
        weakest = (
            ConceptMastery.query.filter_by(student_id=current_user.id)
            .order_by(ConceptMastery.mastery_score.asc()).first()
        )
        lesson = weakest.lesson if weakest else None
    if lesson is None:
        return jsonify({"success": False, "error": "اختاري درسًا للاختبار السريع."}), 400
    session = ChallengeSession(
        student_id=current_user.id,
        lesson_id=lesson.id,
        concept=str(data.get("concept") or "").strip() or None,
        mode="quick_quiz",
        initial_difficulty="medium",
        current_difficulty="medium",
        total_rounds=5,
    )
    db.session.add(session)
    db.session.commit()
    return jsonify({
        "success": True,
        "url": url_for("challenges.play", session_id=session.id),
    })


@teacher_bp.get("/learning-hub")
@login_required
def learning_hub():
    refresh_learning_plan(current_user.id)
    db.session.commit()
    masteries = (
        ConceptMastery.query.filter_by(student_id=current_user.id)
        .order_by(ConceptMastery.mastery_score.asc()).all()
    )
    plan_items = (
        LearningPlanItem.query.filter_by(student_id=current_user.id, status="pending")
        .order_by(LearningPlanItem.priority.desc()).all()
    )
    recommendations = []
    for mastery in masteries[:3]:
        if mastery.mastery_score < 45:
            recommendation_type = "مراجعة مركزة"
            recommendation_text = "ابدئي بشرح مبسط مع المعلم ثم حلي اختبارًا سريعًا."
        elif mastery.mastery_score < 70:
            recommendation_type = "تثبيت الفهم"
            recommendation_text = "استخدمي تلميحًا واحدًا ثم حاولي الإجابة بكلماتك."
        else:
            recommendation_type = "تحدٍّ أعلى"
            recommendation_text = "انتقلي إلى سؤال تحليلي أو مستوى متقدم."
        recommendations.append({
            "type": recommendation_type,
            "text": recommendation_text,
            "concept": mastery.concept,
            "lesson": mastery.lesson,
        })
    return render_template(
        "learning_hub.html",
        masteries=masteries,
        plan_items=plan_items,
        recommendations=recommendations,
    )


def get_owned_plan_item_or_404(item_id):
    item = db.session.get(LearningPlanItem, item_id)
    if item is None:
        abort(404)
    if item.student_id != current_user.id:
        abort(403)
    return item


@teacher_bp.post("/plan-items/<int:item_id>/verify")
@login_required
def verify_plan_item(item_id):
    """Start or resume a five-question mastery check for a plan item."""
    item = get_owned_plan_item_or_404(item_id)
    if item.lesson_id is None:
        return redirect(url_for("teacher.learning_hub"))

    active_session = ChallengeSession.query.filter_by(
        student_id=current_user.id,
        learning_plan_item_id=item.id,
        status="active",
    ).order_by(ChallengeSession.started_at.desc()).first()

    if active_session:
        return redirect(
            url_for("challenges.play", session_id=active_session.id)
        )

    concept = item.title.removeprefix("راجعي مفهوم: ").strip()
    session = ChallengeSession(
        student_id=current_user.id,
        lesson_id=item.lesson_id,
        learning_plan_item_id=item.id,
        concept=concept or None,
        mode="mastery_check",
        initial_difficulty="medium",
        current_difficulty="medium",
        total_rounds=5,
    )
    db.session.add(session)
    db.session.commit()
    return redirect(url_for("challenges.play", session_id=session.id))


@teacher_bp.post("/plan-items/<int:item_id>/complete")
@login_required
def complete_plan_item(item_id):
    """Backward-compatible route: completion now requires verification."""
    return verify_plan_item(item_id)


@teacher_bp.get("/my-points")
@login_required
def my_points():
    transactions = (
        XPTransaction.query
        .filter_by(student_id=current_user.id)
        .order_by(XPTransaction.created_at.desc())
        .limit(100)
        .all()
    )
    labels = {
        "tutor_evaluated_answer": "إجابة قيّمها المعلم الذكي",
        "challenge_answer": "إجابة في التحدي",
        "challenge_completed": "إكمال تحدٍ",
    }
    totals_by_reason = {}
    for transaction in transactions:
        totals_by_reason[transaction.reason] = (
            totals_by_reason.get(transaction.reason, 0)
            + transaction.amount
        )
    return render_template(
        "points_wallet.html",
        transactions=transactions,
        totals_by_reason=totals_by_reason,
        reason_labels=labels,
    )


@teacher_bp.post("/ask")
@login_required
def ask_teacher():
    """Backward-compatible entry point using a persisted tutor conversation."""
    conversation = TutorConversation(
        student_id=current_user.id, title="محادثة تعليمية"
    )
    db.session.add(conversation)
    db.session.commit()
    return send_tutor_message(conversation.id)
