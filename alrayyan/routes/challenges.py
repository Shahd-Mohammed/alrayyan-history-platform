from datetime import datetime, timezone

from flask import (
    Blueprint,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from alrayyan.extensions import db
from alrayyan.models import (
    ChallengeAnswer,
    ChallengeQuestion,
    ChallengeQuestionSource,
    ChallengeSession,
    ConceptMastery,
    ContentChunk,
    LearningPlanItem,
    Lesson,
    Worksheet,
    XPTransaction,
)
from alrayyan.services.challenge_engine import (
    DIFFICULTIES,
    calculate_award,
    choose_next_difficulty,
)
from alrayyan.services.challenge_generator import (
    generate_challenge_question,
    question_similarity_score,
    questions_are_similar,
)


challenges_bp = Blueprint(
    "challenges", __name__, url_prefix="/challenges"
)


def student_required():
    if current_user.role != "student":
        abort(403)


def get_owned_session_or_404(session_id):
    session = db.session.get(ChallengeSession, session_id)
    if session is None:
        abort(404)
    if session.student_id != current_user.id:
        abort(403)
    return session


def serialize_sources(question):
    sources = []
    seen = set()
    for link in question.source_links:
        chunk = link.chunk
        source = chunk.source
        key = (source.id, chunk.page_number, chunk.lesson_id)
        if key in seen:
            continue
        seen.add(key)
        sources.append(
            {
                "title": source.title,
                "lesson_title": (
                    chunk.lesson.title if chunk.lesson else None
                ),
                "page_number": chunk.page_number,
                "is_primary": source.is_primary,
            }
        )
    return sources


def create_question_for_session(session):
    existing = ChallengeQuestion.query.filter_by(
        session_id=session.id,
        round_number=session.current_round,
    ).first()
    if existing:
        return existing

    current_session_questions = [
        item.question_text
        for item in session.questions
        if item.round_number < session.current_round
    ]

    recent_questions = (
        ChallengeQuestion.query
        .join(
            ChallengeSession,
            ChallengeQuestion.session_id
            == ChallengeSession.id,
        )
        .filter(
            ChallengeSession.student_id == session.student_id,
            ChallengeSession.lesson_id == session.lesson_id,
            ChallengeSession.id != session.id,
        )
        .order_by(ChallengeQuestion.created_at.desc())
        .limit(12)
        .all()
    )

    previous_question_texts = list(
        dict.fromkeys(
            current_session_questions
            + [item.question_text for item in recent_questions]
        )
    )

    payload = None
    best_fallback = None
    best_fallback_similarity = 2.0
    rejected_question_texts = []
    last_generation_error = None

    for generation_attempt in range(5):
        try:
            candidate = generate_challenge_question(
                session.lesson,
                session.concept,
                session.current_difficulty,
                previous_question_texts=(
                    previous_question_texts
                    + rejected_question_texts
                ),
                round_number=session.current_round,
                variation_number=generation_attempt,
            )
        except RuntimeError as error:
            last_generation_error = error
            continue

        maximum_similarity = max(
            (
                question_similarity_score(
                    candidate["question_text"],
                    previous_text,
                )
                for previous_text in previous_question_texts
            ),
            default=0.0,
        )

        if maximum_similarity < best_fallback_similarity:
            best_fallback = candidate
            best_fallback_similarity = maximum_similarity

        is_duplicate = any(
            questions_are_similar(
                candidate["question_text"],
                previous_text,
            )
            for previous_text in previous_question_texts
        )

        if not is_duplicate:
            payload = candidate
            break

        rejected_question_texts.append(
            candidate["question_text"]
        )

    if payload is None and best_fallback is not None:
        # A valid grounded question is safer than aborting the whole session.
        # We only use the least-similar candidate after exhausting five angles.
        payload = best_fallback

    if payload is None:
        if last_generation_error:
            raise last_generation_error
        raise RuntimeError(
            "تعذر إنشاء سؤال موثق الآن. يمكنك إعادة المحاولة "
            "من الجولة نفسها دون خسارة تقدمك."
        )
    question = ChallengeQuestion(
        session_id=session.id,
        round_number=session.current_round,
        question_text=payload["question_text"].strip(),
        options_json=payload["options"],
        correct_option_index=payload["correct_option_index"],
        explanation=payload["explanation"].strip(),
        hint_one=payload["hint_one"].strip(),
        hint_two=payload["hint_two"].strip(),
        difficulty=session.current_difficulty,
        concept=payload["concept"].strip(),
        generation_model=payload["model"],
        prompt_version=payload["prompt_version"],
    )
    db.session.add(question)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        existing = ChallengeQuestion.query.filter_by(
            session_id=session.id,
            round_number=session.current_round,
        ).first()
        if existing:
            return existing
        raise

    chunks = ContentChunk.query.filter(
        ContentChunk.id.in_(payload["source_chunk_ids"])
    ).all()
    for chunk in chunks:
        db.session.add(
            ChallengeQuestionSource(
                question_id=question.id,
                chunk_id=chunk.id,
            )
        )

    db.session.commit()
    return question


@challenges_bp.get("/")
@login_required
def setup():
    student_required()
    lessons = (
        Lesson.query
        .join(ContentChunk, ContentChunk.lesson_id == Lesson.id)
        .join(Unit, Unit.id == Lesson.unit_id)
        .join(Curriculum, Curriculum.id == Unit.curriculum_id)
        .filter(
            ContentChunk.embedding.isnot(None),
            Curriculum.is_active.is_(True),
            Curriculum.processing_status == "ready",
            Lesson.title.notin_({
                "محتوى المنهج",
                "الدرس احتياطي",
                "الوحدة — الدرس احتياطي",
            }),
        )
        .distinct()
        .order_by(Curriculum.subject, Curriculum.grade, Unit.order_index, Lesson.order_index)
        .all()
    )
    return render_template("challenge_setup.html", lessons=lessons)


@challenges_bp.get("/test-bank")
@login_required
def test_bank():
    student_required()
    lessons = (
        Lesson.query
        .join(ContentChunk, ContentChunk.lesson_id == Lesson.id)
        .join(Unit, Unit.id == Lesson.unit_id)
        .join(Curriculum, Curriculum.id == Unit.curriculum_id)
        .filter(
            ContentChunk.embedding.isnot(None),
            Curriculum.is_active.is_(True),
            Curriculum.processing_status == "ready",
            Lesson.title.notin_({
                "محتوى المنهج",
                "الدرس احتياطي",
                "الوحدة — الدرس احتياطي",
            }),
        )
        .distinct()
        .order_by(Curriculum.subject, Curriculum.grade, Unit.order_index, Lesson.order_index)
        .all()
    )
    worksheets = (
        Worksheet.query
        .filter_by(
            publication_status="published",
            is_published=True,
        )
        .order_by(Worksheet.created_at.desc())
        .all()
    )
    recent_sessions = (
        ChallengeSession.query
        .filter_by(student_id=current_user.id, status="completed")
        .order_by(ChallengeSession.completed_at.desc())
        .limit(6)
        .all()
    )
    return render_template(
        "test_bank.html",
        lessons=lessons,
        worksheets=worksheets,
        recent_sessions=recent_sessions,
    )


@challenges_bp.post("/start")
@login_required
def start():
    student_required()
    scope_mode = request.form.get("scope_mode", "selected_lesson")
    random_mode = (
        scope_mode == "curriculum_random"
        or request.form.get("random_mode") == "1"
    )
    difficulty = request.form.get("difficulty", "medium")
    concept = (request.form.get("concept") or "").strip() or None

    try:
        total_rounds = int(request.form.get("total_rounds", "5"))
    except ValueError:
        total_rounds = 5
    total_rounds = min(max(total_rounds, 3), 10)

    if difficulty == "adaptive":
        initial_difficulty = "medium"
        mode = "adaptive"
    elif difficulty in DIFFICULTIES:
        initial_difficulty = difficulty
        mode = "random" if random_mode else "lesson"
    else:
        flash("مستوى التحدي غير صالح.", "error")
        return redirect(url_for("challenges.setup"))

    if random_mode:
        lesson = (
            Lesson.query
            .join(ContentChunk, ContentChunk.lesson_id == Lesson.id)
            .join(Unit, Unit.id == Lesson.unit_id)
            .join(Curriculum, Curriculum.id == Unit.curriculum_id)
            .filter(
                ContentChunk.embedding.isnot(None),
                Curriculum.is_active.is_(True),
                Curriculum.processing_status == "ready",
                Lesson.title.notin_({
                    "محتوى المنهج",
                    "الدرس الاحتياطي",
                    "الوحدة — الدرس احتياطي",
                }),
            )
            .order_by(db.func.random())
            .first()
        )
    else:
        raw_lesson_id = request.form.get("lesson_id", "")
        lesson = (
            db.session.get(Lesson, int(raw_lesson_id))
            if raw_lesson_id.isdigit()
            else None
        )

    if lesson is None:
        flash("يرجى اختيار درس يحتوي محتوى قابلًا للبحث.", "error")
        return redirect(url_for("challenges.setup"))

    session = ChallengeSession(
        student_id=current_user.id,
        lesson_id=lesson.id,
        concept=concept,
        mode=mode,
        initial_difficulty=initial_difficulty,
        current_difficulty=initial_difficulty,
        total_rounds=total_rounds,
    )
    db.session.add(session)
    db.session.commit()
    return redirect(url_for("challenges.play", session_id=session.id))


@challenges_bp.get("/<int:session_id>/play")
@login_required
def play(session_id):
    student_required()
    session = get_owned_session_or_404(session_id)
    if session.status == "completed":
        return redirect(url_for("challenges.result", session_id=session.id))

    try:
        question = create_question_for_session(session)
    except RuntimeError as error:
        db.session.rollback()
        return render_template(
            "challenge_generation_error.html",
            challenge=session,
            error_message=str(error),
        ), 503

    return render_template(
        "challenge_play.html",
        challenge=session,
        question=question,
        progress=round((session.current_round - 1) / session.total_rounds * 100),
    )


@challenges_bp.post(
    "/<int:session_id>/questions/<int:question_id>/hint"
)
@login_required
def hint(session_id, question_id):
    student_required()
    session = get_owned_session_or_404(session_id)
    question = db.session.get(ChallengeQuestion, question_id)
    if (
        question is None
        or question.session_id != session.id
        or question.answer is not None
    ):
        abort(404)

    question.hints_used = min(question.hints_used + 1, 2)
    db.session.commit()
    hint_text = (
        question.hint_one
        if question.hints_used == 1
        else question.hint_two
    )
    return jsonify(
        {
            "success": True,
            "hint": hint_text,
            "hints_used": question.hints_used,
        }
    )


@challenges_bp.post(
    "/<int:session_id>/questions/<int:question_id>/answer"
)
@login_required
def answer(session_id, question_id):
    student_required()
    session = get_owned_session_or_404(session_id)
    question = db.session.get(ChallengeQuestion, question_id)
    if question is None or question.session_id != session.id:
        abort(404)
    if question.answer is not None:
        return jsonify(
            {"success": False, "error": "تمت إجابة هذا السؤال مسبقًا."}
        ), 409

    data = request.get_json(silent=True) or {}
    selected_index = data.get("selected_option_index")
    if not isinstance(selected_index, int) or selected_index not in range(4):
        return jsonify(
            {"success": False, "error": "الإجابة المختارة غير صالحة."}
        ), 400

    is_correct = selected_index == question.correct_option_index
    award = calculate_award(
        question.difficulty,
        is_correct,
        question.hints_used,
        session.combo,
    )
    feedback = (
        "إجابة صحيحة. " + question.explanation
        if is_correct
        else "الإجابة غير صحيحة. " + question.explanation
    )
    answer_record = ChallengeAnswer(
        question_id=question.id,
        student_id=current_user.id,
        selected_option_index=selected_index,
        is_correct=is_correct,
        evaluation_status="correct" if is_correct else "incorrect",
        feedback=feedback,
        hints_used=question.hints_used,
        score_awarded=award["score"],
        xp_awarded=award["xp"],
    )
    db.session.add(answer_record)

    session.score += award["score"]
    session.xp_earned += award["xp"]
    session.combo = award["new_combo"]
    session.best_combo = max(session.best_combo, session.combo)
    if is_correct:
        session.correct_count += 1

    mastery = ConceptMastery.query.filter_by(
        student_id=current_user.id,
        lesson_id=session.lesson_id,
        concept=question.concept or "المفهوم العام",
    ).first()

    if mastery is None:
        mastery = ConceptMastery(
            student_id=current_user.id,
            lesson_id=session.lesson_id,
            concept=question.concept or "المفهوم العام",
            mastery_score=50,
            correct_count=0,
            partial_count=0,
            incorrect_count=0,
        )
        db.session.add(mastery)

    if is_correct:
        mastery.mastery_score = min(
            (mastery.mastery_score or 50) + 6,
            100,
        )
        mastery.correct_count = (mastery.correct_count or 0) + 1
    else:
        mastery.mastery_score = max(
            (mastery.mastery_score or 50) - 5,
            0,
        )
        mastery.incorrect_count = (mastery.incorrect_count or 0) + 1

    mastery.last_reviewed_at = datetime.now(timezone.utc)

    session.current_difficulty = choose_next_difficulty(
        session.current_difficulty,
        is_correct,
        question.hints_used,
        session.combo,
    )

    if award["xp"]:
        db.session.add(
            XPTransaction(
                student_id=current_user.id,
                amount=award["xp"],
                reason="challenge_answer",
                source_type="challenge_question",
                source_id=question.id,
            )
        )
        current_user.points += award["xp"]

    completed = session.current_round >= session.total_rounds
    if completed:
        session.status = "completed"
        session.completed_at = datetime.now(timezone.utc)
        completion_xp = 25
        session.xp_earned += completion_xp
        current_user.points += completion_xp
        db.session.add(
            XPTransaction(
                student_id=current_user.id,
                amount=completion_xp,
                reason="challenge_completed",
                source_type="challenge_session",
                source_id=session.id,
            )
        )

        if session.learning_plan_item_id:
            plan_item = db.session.get(
                LearningPlanItem,
                session.learning_plan_item_id,
            )
            if plan_item and plan_item.student_id == current_user.id:
                accuracy = round(
                    session.correct_count / session.total_rounds * 100
                )
                plan_item.verification_score = accuracy
                plan_item.verified_at = datetime.now(timezone.utc)
                if accuracy >= 70:
                    plan_item.status = "completed"
                    plan_item.completed_at = datetime.now(timezone.utc)
                else:
                    plan_item.status = "pending"
    else:
        session.current_round += 1

    current_user.level = max(1, current_user.points // 500 + 1)
    db.session.commit()

    return jsonify(
        {
            "success": True,
            "correct": is_correct,
            "correct_option_index": question.correct_option_index,
            "feedback": feedback,
            "score_awarded": award["score"],
            "xp_awarded": award["xp"],
            "completion_xp": 25 if completed else 0,
            "score": session.score,
            "xp_total": session.xp_earned,
            "combo": session.combo,
            "next_difficulty": session.current_difficulty,
            "sources": serialize_sources(question),
            "completed": completed,
            "next_url": url_for(
                "challenges.result" if completed else "challenges.play",
                session_id=session.id,
            ),
        }
    )


@challenges_bp.get("/<int:session_id>/result")
@login_required
def result(session_id):
    student_required()
    session = get_owned_session_or_404(session_id)
    if session.status != "completed":
        return redirect(url_for("challenges.play", session_id=session.id))
    accuracy = round(session.correct_count / session.total_rounds * 100)
    return render_template(
        "challenge_result.html",
        challenge=session,
        accuracy=accuracy,
        plan_item=session.learning_plan_item,
    )
