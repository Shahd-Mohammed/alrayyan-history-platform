from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import re

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required

from alrayyan.extensions import db
from alrayyan.models import (
    ChallengeSession, ConceptMastery, ContentChunk, Curriculum, LearningPlanItem,
    Lesson, TutorConversation, TutorMessage, TutorMessageSource, Unit,
    XPTransaction,
)
from alrayyan.services.grade_access import (lessons_for_user, student_can_access_lesson, student_available_grades, student_grade, normalize_grade)
from alrayyan.services.tutor_engine import preserve_concept_for_evaluated_answer, tutor_reply
from alrayyan.services.datetime_utils import as_utc_naive


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


@teacher_bp.get("/select-grade/<grade>")
@login_required
def select_student_grade(grade):
    """Let a student switch only to a grade where they have an active enrollment."""
    if current_user.role != "student":
        abort(403)
    normalized = normalize_grade(grade)
    if normalized not in student_available_grades(current_user):
        abort(404)
    session["student_selected_grade"] = normalized
    next_path = request.args.get("next", "")
    if next_path.startswith("/") and not next_path.startswith("//"):
        return redirect(next_path)
    return redirect(url_for("teacher.teacher_page"))


def get_owned_conversation_or_404(conversation_id):
    conversation = db.session.get(TutorConversation, conversation_id)
    if conversation is None:
        abort(404)
    if conversation.student_id != current_user.id:
        abort(403)
    if conversation.lesson is not None and not student_can_access_lesson(current_user, conversation.lesson):
        abort(404)
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


def preserve_failed_tutor_message(conversation_id, student_text):
    """Keep the student's question even when an external AI request fails."""
    if not student_text:
        return
    try:
        db.session.rollback()
        conversation = db.session.get(TutorConversation, conversation_id)
        if conversation is None:
            return
        last_message = conversation.messages[-1] if conversation.messages else None
        if not (
            last_message
            and last_message.role == "student"
            and last_message.content == student_text
        ):
            db.session.add(TutorMessage(
                conversation_id=conversation.id,
                role="student",
                content=student_text,
            ))
            conversation.updated_at = utc_now()
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Could not preserve student message after tutor failure"
        )


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
            mastery_score=0,
            correct_count=0,
            partial_count=0,
            incorrect_count=0,
        )
        db.session.add(mastery)
    mastery.mastery_score = min(max(
        (mastery.mastery_score or 0) + payload["mastery_delta"], 0
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
            and mastery.last_reviewed_at
            and as_utc_naive(mastery.last_reviewed_at) <= as_utc_naive(existing.completed_at)
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
    # The AI teacher must follow the same active-curriculum rule as
    # teacher-facing lesson selectors. Legacy indexed lessons from an
    # inactive semester must never appear here.
    lessons = (
        Lesson.query
        .join(ContentChunk, ContentChunk.lesson_id == Lesson.id)
        .join(Unit, Unit.id == Lesson.unit_id)
        .join(Curriculum, Curriculum.id == Unit.curriculum_id)
        .filter(
            ContentChunk.embedding.isnot(None),
            Curriculum.is_active.is_(True),
            Curriculum.processing_status == "ready",
            # Exclude legacy placeholder lessons left by the old PDF parser.
            Lesson.title.notin_({
                "محتوى المنهج",
                "الدرس احتياطي",
                "الوحدة — الدرس احتياطي",
            }),
            Lesson.id.in_(lessons_for_user(current_user, active_only=True) or [-1]),
        )
        # Group by the lesson and sort keys instead of DISTINCT: PostgreSQL
        # rejects ORDER BY columns that are not selected with SELECT DISTINCT.
        .group_by(
            Lesson.id,
            Curriculum.subject,
            Curriculum.grade,
            Unit.order_index,
            Lesson.order_index,
        )
        .order_by(Curriculum.subject, Curriculum.grade, Unit.order_index, Lesson.order_index)
        .all()
    )
    conversations = (
        TutorConversation.query.filter_by(student_id=current_user.id)
        .order_by(TutorConversation.updated_at.desc()).limit(10).all()
    )
    raw_lesson_id = request.args.get("lesson_id", "")
    requested_lesson_id = int(raw_lesson_id) if raw_lesson_id.isdigit() else None
    available_lesson_ids = {lesson.id for lesson in lessons}
    initial_lesson_id = (
        requested_lesson_id
        if requested_lesson_id in available_lesson_ids
        else None
    )
    initial_concept = (request.args.get("concept") or "").strip()[:250]
    review_mode = request.args.get("mode") == "review"
    review_lesson_available = initial_lesson_id is not None
    return render_template(
        "teacher.html",
        lessons=lessons,
        conversations=conversations,
        initial_lesson_id=initial_lesson_id,
        initial_concept=initial_concept,
        review_mode=review_mode,
        review_lesson_available=review_lesson_available,
        available_grades=student_available_grades(current_user),
        selected_student_grade=student_grade(current_user),
    )


@teacher_bp.post("/conversations")
@login_required
def create_conversation():
    data = request.get_json(silent=True) or {}
    raw_lesson_id = str(data.get("lesson_id") or "")
    lesson = db.session.get(Lesson, int(raw_lesson_id)) if raw_lesson_id.isdigit() else None
    if lesson is not None and not student_can_access_lesson(current_user, lesson):
        abort(404)
    initial_concept = str(data.get("concept") or "").strip()[:250] or None

    # When a review is launched from the learning plan, resume the student's
    # latest conversation that already covered this exact lesson and concept.
    if lesson is not None and initial_concept:
        previous_conversation = (
            TutorConversation.query
            .join(
                TutorMessage,
                TutorMessage.conversation_id == TutorConversation.id,
            )
            .filter(
                TutorConversation.student_id == current_user.id,
                TutorConversation.lesson_id == lesson.id,
                TutorMessage.concept == initial_concept,
            )
            .order_by(TutorConversation.updated_at.desc())
            .first()
        )
        if previous_conversation is not None:
            return jsonify({
                "success": True,
                "conversation_id": previous_conversation.id,
                "title": previous_conversation.title,
                "lesson_id": previous_conversation.lesson_id,
                "concept": previous_conversation.current_concept,
                "messages": [
                    serialize_message(item)
                    for item in previous_conversation.messages
                ],
                "resumed": True,
            })

    conversation = TutorConversation(
        student_id=current_user.id,
        lesson_id=lesson.id if lesson else None,
        title=(
            f"مراجعة {initial_concept} — {lesson.title}"
            if lesson is not None and initial_concept
            else f"مراجعة {lesson.title}"
            if lesson
            else "محادثة تعليمية جديدة"
        ),
        difficulty=data.get("difficulty", "adaptive"),
        current_concept=initial_concept,
    )
    db.session.add(conversation)
    db.session.flush()
    if initial_concept and lesson:
        opening_message = (
            f"يا هلا {current_user.first_name}، خلّينا نراجع «{initial_concept}» "
            f"من درس «{lesson.title}» خطوة خطوة. بنبدأ بفكرة بسيطة، وبعدها بنتدرّب على إجابتك."
        )
    elif lesson:
        opening_message = (
            f"تمام، اخترنا درس «{lesson.title}». خلّينا نبدأ بسؤال خفيف: "
            "شو أول فكرة بتتذكريها من الدرس؟ خذي وقتك، وبنرتّبها سوا."
        )
    else:
        opening_message = (
            f"أهلًا {current_user.first_name}، يا هلا فيك. اختاري درس من القائمة "
            "أو اكتبي الفكرة اللي بدك تفهميها، وبنبلّش من الأساس خطوة خطوة."
        )

    greeting = TutorMessage(
        conversation_id=conversation.id,
        role="tutor",
        action="ask_diagnostic",
        evaluation="not_evaluated",
        content=opening_message,
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


@teacher_bp.post("/conversations/<int:conversation_id>/delete")
@login_required
def delete_tutor_conversation(conversation_id):
    """Delete only the signed-in student's own conversation and its messages."""
    conversation = db.session.get(TutorConversation, conversation_id)
    if conversation is None:
        abort(404)
    if conversation.student_id != current_user.id:
        abort(403)

    db.session.delete(conversation)
    db.session.commit()
    return jsonify({"success": True, "conversation_id": conversation_id})


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
        last_message = conversation.messages[-1] if conversation.messages else None
        if (
            last_message
            and last_message.role == "student"
            and last_message.content == student_text
        ):
            # Reuse a previously saved question when the student retries after an AI error.
            student_message = last_message
        else:
            student_message = TutorMessage(
                conversation_id=conversation.id, role="student", content=student_text
            )
            db.session.add(student_message)
            db.session.flush()
        previous_tutor_state = conversation.tutor_state
        was_verifying_mastery = previous_tutor_state == "verify_mastery"
        payload = tutor_reply(conversation, student_text)
        payload = preserve_concept_for_evaluated_answer(
            conversation.current_concept,
            previous_tutor_state,
            payload,
        )
        awaiting_mastery_verification = (
            was_verifying_mastery
            and payload["evaluation"] != "correct"
            and payload["action"] in {"ask_diagnostic", "ask_follow_up", "give_hint"}
        )

        # A correct or partly correct first answer is not enough to award mastery.
        # Keep the student on the same concept until a correct verification answer.
        if payload["evaluation"] in {"correct", "partially_correct"} and not was_verifying_mastery:
            payload["evaluation"] = "not_evaluated"
            payload["mastery_delta"] = 0
            payload["action"] = "ask_follow_up"
            # The model may include a reward claim in its prose. Do not show points
            # unless this route actually records them in the database.
            payload["reply"] = re.sub(
                r"إجابة\s+صحيحة\s*(?:\+\s*5\s*XP)?|\+\s*5\s*XP",
                "",
                payload["reply"],
                flags=re.IGNORECASE,
            ).strip()
            if "؟" not in payload["reply"] and "?" not in payload["reply"]:
                payload["reply"] += (
                    "\n\nللتأكد من ثبات الفهم، جاوبي بجملة واحدة: "
                    "ما السبب أو الدليل الذي يدعم إجابتكِ؟"
                )
            awaiting_mastery_verification = True

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
        conversation.tutor_state = (
            "verify_mastery" if awaiting_mastery_verification else payload["action"]
        )
        conversation.updated_at = utc_now()
        if conversation.title == "محادثة تعليمية جديدة":
            conversation.title = student_text[:80]
        mastery = update_mastery(conversation, payload)
        # AI-tutor XP is awarded only for a correct answer to the verification question.
        xp_awarded = 5 if (
            was_verifying_mastery and payload["evaluation"] == "correct"
        ) else 0
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

        # A conversation without a selected lesson cannot update a lesson-specific
        # mastery row. Still record a real verified success in the learning plan.
        if xp_awarded and conversation.lesson_id is None:
            concept_title = (
                payload.get("concept")
                or conversation.current_concept
                or student_text
                or "مراجعة عامة"
            ).strip()[:100]
            plan_title = f"راجعي من محادثة المعلّم الذكي: {concept_title}"
            plan_item = LearningPlanItem.query.filter_by(
                student_id=current_user.id,
                lesson_id=None,
                item_type="tutor_review",
                title=plan_title,
                status="pending",
            ).order_by(LearningPlanItem.created_at.desc()).first()
            plan_description = (
                "أكملتِ إجابة تحقق صحيحة في محادثة المعلّم الذكي وحصلتِ على 5 نقاط. "
                "اختاري الدرس المرتبط بهذا المفهوم في محادثة لاحقة حتى يُسجّل إتقانك ضمن الدرس."
            )
            if plan_item:
                plan_item.description = plan_description
                plan_item.priority = 65
            else:
                db.session.add(LearningPlanItem(
                    student_id=current_user.id,
                    lesson_id=None,
                    item_type="tutor_review",
                    title=plan_title,
                    description=plan_description,
                    priority=65,
                ))
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
        current_app.logger.exception("Interactive tutor request failed")
        preserve_failed_tutor_message(conversation_id, student_text)
        return jsonify({"success": False, "error": str(error)}), 502
    except Exception:
        current_app.logger.exception("Unexpected interactive tutor error")
        preserve_failed_tutor_message(conversation_id, student_text)
        return jsonify({"success": False, "error": "حدث خطأ غير متوقع. حاولي مرة أخرى."}), 500


@teacher_bp.post("/quick-quiz/start")
@login_required
def start_quick_quiz():
    if current_user.role != "student":
        abort(403)
    data = request.get_json(silent=True) or {}
    visible_lesson_ids = set(lessons_for_user(current_user, active_only=True))
    raw_lesson_id = str(data.get("lesson_id") or "")
    lesson = db.session.get(Lesson, int(raw_lesson_id)) if raw_lesson_id.isdigit() else None
    if lesson is not None and lesson.id not in visible_lesson_ids:
        return jsonify({"success": False, "error": "هذا الدرس ليس ضمن صفك الدراسي."}), 403
    if lesson is None:
        weakest = (
            ConceptMastery.query.filter_by(student_id=current_user.id)
            .filter(ConceptMastery.lesson_id.in_(visible_lesson_ids or [-1]))
            .order_by(ConceptMastery.mastery_score.asc()).first()
        )
        lesson = weakest.lesson if weakest else None
    if lesson is None:
        return jsonify({"success": False, "error": "اختاري درسًا من صفك للاختبار السريع."}), 400
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
        .order_by(
            ConceptMastery.last_reviewed_at.desc(),
            ConceptMastery.mastery_score.asc(),
            ConceptMastery.id.desc(),
        ).all()
    )
    plan_items = (
        LearningPlanItem.query.filter_by(student_id=current_user.id, status="pending")
        .order_by(
            LearningPlanItem.created_at.desc(),
            LearningPlanItem.priority.desc(),
        ).all()
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
    all_transactions = XPTransaction.query.filter_by(
        student_id=current_user.id
    ).all()
    transactions = (
        XPTransaction.query
        .filter_by(student_id=current_user.id)
        .order_by(XPTransaction.created_at.desc())
        .limit(100)
        .all()
    )
    labels = {
        "tutor_evaluated_answer": "إجابة تحقق صحيحة مع المعلّم الذكي",
        "challenge_answer": "إجابة في التحدي",
        "challenge_completed": "إكمال تحدٍ",
        "character_identified": "التعرّف على شخصية تاريخية",
        "concept_map_viewed": "استكشاف خريطة مفاهيمية",
        "resource_downloaded": "تنزيل مادة تعليمية",
        "learning_library_opened": "زيارة مكتبة التعلّم لأول مرة",
        "test_completed": "إكمال اختبار",
        "worksheet_completed": "إكمال ورقة عمل",
        "historical_date_recalled": "تذكّر تاريخ تاريخي",
    }
    totals_by_reason = {}
    for transaction in all_transactions:
        totals_by_reason[transaction.reason] = (
            totals_by_reason.get(transaction.reason, 0)
            + transaction.amount
        )
    palestine_tz = ZoneInfo("Asia/Gaza")
    transaction_times = {}
    for transaction in transactions:
        timestamp = transaction.created_at
        if timestamp is None:
            transaction_times[transaction.id] = "—"
            continue
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        transaction_times[transaction.id] = timestamp.astimezone(
            palestine_tz
        ).strftime("%Y-%m-%d %H:%M")

    return render_template(
        "points_wallet.html",
        transactions=transactions,
        totals_by_reason=totals_by_reason,
        reason_labels=labels,
        transaction_times=transaction_times,
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
