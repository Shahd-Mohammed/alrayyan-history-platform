from datetime import (
    datetime,
    timedelta,
    timezone,
)
from functools import wraps

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

from flask_login import (
    current_user,
    login_required,
)

from alrayyan.extensions import db

from alrayyan.forms import (
    QuestionForm,
    WorksheetSettingsForm,
)

from alrayyan.models import (
    Choice,
    Question,
    StudentAnswer,
    Worksheet,
    WorksheetAttempt,
)


assessment_bp = Blueprint(
    "assessment",
    __name__,
    url_prefix="/assessment",
)


def teacher_required(view_function):
    """
    Allow only teachers and administrators
    to access assessment management pages.
    """

    @wraps(view_function)
    @login_required
    def wrapped_view(*args, **kwargs):
        if current_user.role not in {
            "teacher",
            "admin",
        }:
            abort(403)

        return view_function(
            *args,
            **kwargs,
        )

    return wrapped_view


def get_teacher_worksheet_or_404(
    worksheet_id,
):
    """
    Return the requested worksheet only if
    the current teacher owns it.

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


def normalize_answer(value):
    """
    Normalize spaces and letter casing before
    comparing answers.
    """

    return " ".join(
        (value or "")
        .strip()
        .casefold()
        .split()
    )


def get_next_question_order(worksheet):
    """
    Return the next available question order.

    Using the maximum order prevents conflicts
    after deleting an earlier question.
    """

    current_orders = [
        question.order_index
        for question in worksheet.questions
    ]

    return max(
        current_orders,
        default=0,
    ) + 1


def utc_now():
    """
    Return a timezone-naive UTC datetime.

    SQLite removes timezone information from
    stored DateTime values, so using naive UTC
    keeps all comparisons consistent.
    """

    return datetime.now(
        timezone.utc
    ).replace(
        tzinfo=None
    )


def get_attempt_deadline(attempt):
    """
    Return the deadline for a timed attempt.

    A worksheet without a time limit has no
    deadline and returns None.
    """

    time_limit = (
        attempt
        .worksheet
        .time_limit_minutes
    )

    if not time_limit:
        return None

    started_at = attempt.started_at

    if started_at.tzinfo is not None:
        started_at = (
            started_at
            .astimezone(timezone.utc)
            .replace(tzinfo=None)
        )

    return started_at + timedelta(
        minutes=time_limit
    )


def get_remaining_seconds(attempt):
    """
    Return the number of whole seconds left
    in an attempt.
    """

    deadline = get_attempt_deadline(
        attempt
    )

    if deadline is None:
        return None

    remaining = int(
        (
            deadline
            - utc_now()
        ).total_seconds()
    )

    return max(
        remaining,
        0,
    )


def attempt_time_has_expired(attempt):
    """
    Check whether a timed attempt has ended.
    """

    remaining_seconds = (
        get_remaining_seconds(
            attempt
        )
    )

    return (
        remaining_seconds is not None
        and remaining_seconds <= 0
    )


def get_or_create_student_answer(
    attempt,
    question,
):
    """
    Return the existing draft answer or create
    one for this attempt and question.
    """

    student_answer = (
        StudentAnswer.query
        .filter_by(
            attempt_id=attempt.id,
            question_id=question.id,
        )
        .first()
    )

    if student_answer is None:
        student_answer = StudentAnswer(
            attempt_id=attempt.id,
            question_id=question.id,
            awarded_points=0.0,
        )

        db.session.add(
            student_answer
        )

    return student_answer


def save_attempt_draft(
    attempt,
    submitted_form,
):
    """
    Save the student's current form values
    without submitting or grading the attempt.
    """

    for question in attempt.worksheet.questions:
        field_name = (
            f"question_{question.id}"
        )

        if field_name not in submitted_form:
            continue

        submitted_value = (
            submitted_form.get(
                field_name,
                "",
            )
        )

        if isinstance(
            submitted_value,
            str,
        ):
            submitted_value = (
                submitted_value.strip()
            )

        student_answer = (
            get_or_create_student_answer(
                attempt,
                question,
            )
        )

        if (
            question.question_type
            == "multiple_choice"
        ):
            selected_choice = None

            if (
                submitted_value
                and submitted_value.isdigit()
            ):
                selected_choice = (
                    Choice.query
                    .filter_by(
                        id=int(
                            submitted_value
                        ),
                        question_id=question.id,
                    )
                    .first()
                )

            student_answer.selected_choice_id = (
                selected_choice.id
                if selected_choice
                else None
            )

            student_answer.answer_text = None

        else:
            student_answer.selected_choice_id = (
                None
            )

            student_answer.answer_text = (
                submitted_value
            )

        student_answer.is_correct = None
        student_answer.awarded_points = 0.0
        student_answer.answered_at = utc_now()


def grade_and_submit_attempt(
    attempt,
):
    """
    Grade saved answers and permanently submit
    the attempt.
    """

    for question in attempt.worksheet.questions:
        student_answer = (
            get_or_create_student_answer(
                attempt,
                question,
            )
        )

        student_answer.is_correct = None
        student_answer.awarded_points = 0.0

        if (
            question.question_type
            == "multiple_choice"
        ):
            selected_choice = None

            if student_answer.selected_choice_id:
                selected_choice = (
                    Choice.query
                    .filter_by(
                        id=(
                            student_answer
                            .selected_choice_id
                        ),
                        question_id=question.id,
                    )
                    .first()
                )

            student_answer.is_correct = bool(
                selected_choice
                and selected_choice.is_correct
            )

            if student_answer.is_correct:
                student_answer.awarded_points = (
                    question.points
                )

        elif question.question_type in {
            "true_false",
            "short_answer",
        }:
            student_answer.is_correct = (
                normalize_answer(
                    student_answer.answer_text
                    or ""
                )
                == normalize_answer(
                    question.correct_answer_text
                    or ""
                )
            )

            if student_answer.is_correct:
                student_answer.awarded_points = (
                    question.points
                )

        elif (
            question.question_type
            == "essay"
        ):
            student_answer.is_correct = None
            student_answer.awarded_points = 0.0

        student_answer.answered_at = utc_now()

    attempt.submitted_at = utc_now()

    db.session.flush()

    calculate_attempt_result(
        attempt
    )

    db.session.commit()


def build_saved_answers(attempt):
    """
    Prepare saved answers for the Jinja template.
    """

    saved_answers = {}

    for answer in attempt.answers:
        if answer.selected_choice_id:
            saved_answers[
                answer.question_id
            ] = str(
                answer.selected_choice_id
            )
        else:
            saved_answers[
                answer.question_id
            ] = (
                answer.answer_text
                or ""
            )

    return saved_answers
@assessment_bp.route(
    "/teacher/worksheets/"
    "<int:worksheet_id>/questions",
    methods=["GET", "POST"],
)
@teacher_required
def manage_questions(worksheet_id):
    """
    Display the worksheet questions and allow
    the teacher to add a new question.
    """

    worksheet = (
        get_teacher_worksheet_or_404(
            worksheet_id
        )
    )

    form = QuestionForm()

    settings_form = WorksheetSettingsForm(
        obj=worksheet
    )

    if form.validate_on_submit():
        question_type = (
            form.question_type.data
        )

        choices = [
            line.strip()
            for line
            in (
                form.choices_text.data
                or ""
            ).splitlines()
            if line.strip()
        ]

        correct_answer = (
            form.correct_answer_text.data
            or ""
        ).strip()

        if question_type == "multiple_choice":
            if len(choices) < 2:
                flash(
                    (
                        "سؤال الاختيار من متعدد "
                        "يحتاج خيارين على الأقل."
                    ),
                    "error",
                )

                return render_template(
                    "manage_questions.html",
                    worksheet=worksheet,
                    form=form,
                    settings_form=settings_form,
                )

            normalized_choices = {
                normalize_answer(choice)
                for choice in choices
            }

            if (
                normalize_answer(
                    correct_answer
                )
                not in normalized_choices
            ):
                flash(
                    (
                        "الإجابة الصحيحة يجب أن "
                        "تطابق أحد الخيارات تمامًا."
                    ),
                    "error",
                )

                return render_template(
                    "manage_questions.html",
                    worksheet=worksheet,
                    form=form,
                    settings_form=settings_form,
                )

        if question_type == "true_false":
            if normalize_answer(
                correct_answer
            ) not in {
                "صح",
                "خطأ",
            }:
                flash(
                    (
                        "في سؤال الصح والخطأ "
                        "اكتبي الإجابة: صح أو خطأ."
                    ),
                    "error",
                )

                return render_template(
                    "manage_questions.html",
                    worksheet=worksheet,
                    form=form,
                    settings_form=settings_form,
                )

        if (
            question_type == "short_answer"
            and not correct_answer
        ):
            flash(
                (
                    "يرجى كتابة الإجابة الصحيحة "
                    "لسؤال الإجابة القصيرة."
                ),
                "error",
            )

            return render_template(
                "manage_questions.html",
                worksheet=worksheet,
                form=form,
                settings_form=settings_form,
            )

        question = Question(
            worksheet_id=worksheet.id,
            question_text=(
                form.question_text.data.strip()
            ),
            question_type=question_type,
            correct_answer_text=(
                correct_answer or None
            ),
            explanation=(
                form.explanation.data.strip()
                if form.explanation.data
                else None
            ),
            points=form.points.data,
            order_index=(
                get_next_question_order(
                    worksheet
                )
            ),
            requires_manual_grading=(
                question_type == "essay"
            ),
        )

        db.session.add(question)
        db.session.flush()

        if question_type == "multiple_choice":
            for index, choice_text in enumerate(
                choices,
                start=1,
            ):
                choice = Choice(
                    question_id=question.id,
                    choice_text=choice_text,
                    is_correct=(
                        normalize_answer(
                            choice_text
                        )
                        == normalize_answer(
                            correct_answer
                        )
                    ),
                    order_index=index,
                )

                db.session.add(choice)

        db.session.commit()

        flash(
            "تمت إضافة السؤال بنجاح.",
            "success",
        )

        return redirect(
            url_for(
                "assessment.manage_questions",
                worksheet_id=worksheet.id,
            )
        )

    return render_template(
        "manage_questions.html",
        worksheet=worksheet,
        form=form,
        settings_form=settings_form,
    )


@assessment_bp.post(
    "/teacher/worksheets/"
    "<int:worksheet_id>/settings"
)
@teacher_required
def save_worksheet_settings(
    worksheet_id,
):
    """
    Save the interactive worksheet settings.
    """

    worksheet = (
        get_teacher_worksheet_or_404(
            worksheet_id
        )
    )

    form = WorksheetSettingsForm()

    if not form.validate_on_submit():
        for errors in form.errors.values():
            for error in errors:
                flash(
                    error,
                    "error",
                )

        return redirect(
            url_for(
                "assessment.manage_questions",
                worksheet_id=worksheet.id,
            )
        )

    worksheet.time_limit_minutes = (
        form.time_limit_minutes.data
    )

    worksheet.passing_score = (
        form.passing_score.data
    )

    worksheet.max_attempts = (
        form.max_attempts.data
    )

    worksheet.allow_multiple_attempts = (
        form.max_attempts.data > 1
    )

    worksheet.show_answers_after_submit = bool(
        form.show_answers_after_submit.data
    )

    db.session.commit()

    flash(
        "تم حفظ إعدادات الحل بنجاح.",
        "success",
    )

    return redirect(
        url_for(
            "assessment.manage_questions",
            worksheet_id=worksheet.id,
        )
    )


@assessment_bp.post(
    "/teacher/questions/"
    "<int:question_id>/delete"
)
@teacher_required
def delete_question(question_id):
    """
    Delete a question owned by the current
    teacher.
    """

    question = db.session.get(
        Question,
        question_id,
    )

    if question is None:
        abort(404)

    worksheet = (
        get_teacher_worksheet_or_404(
            question.worksheet_id
        )
    )
    has_student_answers = (
        StudentAnswer.query
        .filter_by(
            question_id=question.id
        )
        .first()
        is not None
    )

    if has_student_answers:
        flash(
            (
                "لا يمكن حذف هذا السؤال "
                "لوجود نتائج طلاب مرتبطة به. "
                "يمكنك تعديل نصه وشرحه فقط."
            ),
            "error",
        )

        return redirect(
            url_for(
                "assessment.manage_questions",
                worksheet_id=worksheet.id,
            )
        )

    db.session.delete(question)
    db.session.commit()

    flash(
        "تم حذف السؤال بنجاح.",
        "success",
    )

    return redirect(
        url_for(
            "assessment.manage_questions",
            worksheet_id=worksheet.id,
        )
    )


def get_published_worksheet_or_404(
    worksheet_id,
):
    """
    Return a worksheet only when it is
    published and available to students.
    """

    return (
        Worksheet.query
        .filter_by(
            id=worksheet_id,
            publication_status="published",
            is_published=True,
        )
        .first_or_404()
    )


def get_student_attempt_or_404(
    attempt_id,
):
    """
    Return an attempt only when it belongs
    to the currently logged-in student.
    """

    attempt = db.session.get(
        WorksheetAttempt,
        attempt_id,
    )

    if attempt is None:
        abort(404)

    if (
        current_user.role != "student"
        or attempt.student_id
        != current_user.id
    ):
        abort(403)

    return attempt


def calculate_attempt_result(attempt):
    """
    Recalculate the score and percentage
    using all saved answers.
    """

    attempt.score = sum(
        answer.awarded_points
        for answer in attempt.answers
    )

    attempt.max_score = (
        attempt.worksheet.total_points()
    )

    if attempt.max_score:
        attempt.percentage = (
            attempt.score
            / attempt.max_score
            * 100
        )
    else:
        attempt.percentage = 0.0

    has_pending_manual_grading = any(
        answer.is_correct is None
        for answer in attempt.answers
    )

    attempt.is_passed = (
        not has_pending_manual_grading
        and attempt.percentage
        >= attempt.worksheet.passing_score
    )


@assessment_bp.post(
    "/worksheets/<int:worksheet_id>/start"
)
@login_required
def start_attempt(worksheet_id):
    """
    Create a new student attempt or continue
    an unfinished attempt.
    """

    if current_user.role != "student":
        flash(
            "الحل التفاعلي مخصص لحساب الطالب.",
            "info",
        )

        return redirect(
            url_for(
                "worksheets.worksheet_details",
                worksheet_id=worksheet_id,
            )
        )

    worksheet = (
        get_published_worksheet_or_404(
            worksheet_id
        )
    )

    if not worksheet.questions:
        flash(
            (
                "لم تضف المعلمة أسئلة "
                "تفاعلية لهذه الورقة بعد."
            ),
            "info",
        )

        return redirect(
            url_for(
                "worksheets.worksheet_details",
                worksheet_id=worksheet.id,
            )
        )

    open_attempt = (
        WorksheetAttempt.query
        .filter_by(
            worksheet_id=worksheet.id,
            student_id=current_user.id,
            submitted_at=None,
        )
        .first()
    )

    if open_attempt:
        return redirect(
            url_for(
                "assessment.solve_attempt",
                attempt_id=open_attempt.id,
            )
        )

    submitted_attempts_count = (
        WorksheetAttempt.query
        .filter_by(
            worksheet_id=worksheet.id,
            student_id=current_user.id,
        )
        .filter(
            WorksheetAttempt
            .submitted_at
            .isnot(None)
        )
        .count()
    )

    if (
        submitted_attempts_count
        >= worksheet.max_attempts
    ):
        latest_attempt = (
            WorksheetAttempt.query
            .filter_by(
                worksheet_id=worksheet.id,
                student_id=current_user.id,
            )
            .filter(
                WorksheetAttempt
                .submitted_at
                .isnot(None)
            )
            .order_by(
                WorksheetAttempt
                .submitted_at
                .desc()
            )
            .first()
        )

        flash(
            (
                "لقد استخدمتِ جميع المحاولات "
                "المسموح بها لهذه الورقة "
                f"({worksheet.max_attempts})."
            ),
            "info",
        )

        return redirect(
            url_for(
                "assessment.attempt_result",
                attempt_id=latest_attempt.id,
            )
        )

    attempt = WorksheetAttempt(
        worksheet_id=worksheet.id,
        student_id=current_user.id,
        max_score=worksheet.total_points(),
    )

    db.session.add(attempt)
    db.session.commit()

    return redirect(
        url_for(
            "assessment.solve_attempt",
            attempt_id=attempt.id,
        )
    )


@assessment_bp.post(
    "/attempts/<int:attempt_id>/autosave"
)
@login_required
def autosave_attempt(attempt_id):
    """
    Save draft answers while the student is
    solving the worksheet.
    """

    attempt = get_student_attempt_or_404(
        attempt_id
    )

    if attempt.submitted_at:
        return jsonify(
            {
                "saved": False,
                "submitted": True,
                "message": (
                    "تم تسليم هذه المحاولة مسبقًا."
                ),
                "redirect_url": url_for(
                    "assessment.attempt_result",
                    attempt_id=attempt.id,
                ),
            }
        ), 409

    save_attempt_draft(
        attempt,
        request.form,
    )

    if attempt_time_has_expired(attempt):
        grade_and_submit_attempt(attempt)

        return jsonify(
            {
                "saved": True,
                "submitted": True,
                "time_expired": True,
                "message": (
                    "انتهى الوقت وتم تسليم "
                    "إجاباتك تلقائيًا."
                ),
                "redirect_url": url_for(
                    "assessment.attempt_result",
                    attempt_id=attempt.id,
                ),
            }
        )

    db.session.commit()

    return jsonify(
        {
            "saved": True,
            "submitted": False,
            "remaining_seconds": (
                get_remaining_seconds(attempt)
            ),
            "message": (
                "تم حفظ إجاباتك تلقائيًا."
            ),
        }
    )


@assessment_bp.route(
    "/attempts/<int:attempt_id>/solve",
    methods=["GET", "POST"],
)
@login_required
def solve_attempt(attempt_id):
    """
    Display, autosave, grade, and submit one
    student worksheet attempt.
    """

    attempt = get_student_attempt_or_404(
        attempt_id
    )

    if attempt.submitted_at:
        return redirect(
            url_for(
                "assessment.attempt_result",
                attempt_id=attempt.id,
            )
        )

    worksheet = attempt.worksheet

    if request.method == "POST":
        save_attempt_draft(
            attempt,
            request.form,
        )

        time_expired = attempt_time_has_expired(
            attempt
        )

        grade_and_submit_attempt(attempt)

        if time_expired:
            flash(
                (
                    "انتهى وقت الحل وتم تسليم "
                    "إجاباتك تلقائيًا."
                ),
                "info",
            )
        else:
            flash(
                (
                    "تم تسليم الإجابات "
                    "وحفظ النتيجة بنجاح."
                ),
                "success",
            )

        return redirect(
            url_for(
                "assessment.attempt_result",
                attempt_id=attempt.id,
            )
        )

    if attempt_time_has_expired(attempt):
        grade_and_submit_attempt(attempt)

        flash(
            (
                "انتهى وقت هذه المحاولة، "
                "وتم تسليم آخر إجابات "
                "محفوظة تلقائيًا."
            ),
            "info",
        )

        return redirect(
            url_for(
                "assessment.attempt_result",
                attempt_id=attempt.id,
            )
        )

    return render_template(
        "solve_worksheet.html",
        attempt=attempt,
        worksheet=worksheet,
        saved_answers=(
            build_saved_answers(attempt)
        ),
        remaining_seconds=(
            get_remaining_seconds(attempt)
        ),
    )


@assessment_bp.get(
    "/attempts/<int:attempt_id>/result"
)
@login_required
def attempt_result(attempt_id):
    """
    Display the result of one submitted
    student attempt.
    """

    attempt = (
        get_student_attempt_or_404(
            attempt_id
        )
    )

    if not attempt.submitted_at:
        return redirect(
            url_for(
                "assessment.solve_attempt",
                attempt_id=attempt.id,
            )
        )

    pending_manual_grading = any(
        answer.is_correct is None
        for answer in attempt.answers
    )

    return render_template(
        "attempt_result.html",
        attempt=attempt,
        pending_manual_grading=(
            pending_manual_grading
        ),
    )


@assessment_bp.get("/my-results")
@login_required
def my_results():
    """
    Display all attempts belonging to the
    current student.
    """

    if current_user.role != "student":
        abort(403)

    attempts = (
        WorksheetAttempt.query
        .filter_by(
            student_id=current_user.id
        )
        .order_by(
            WorksheetAttempt
            .started_at
            .desc()
        )
        .all()
    )

    return render_template(
        "student_results.html",
        attempts=attempts,
    )


@assessment_bp.route(
    "/teacher/questions/"
    "<int:question_id>/edit",
    methods=["GET", "POST"],
)
@teacher_required
def edit_question(question_id):
    """
    Edit a worksheet question.

    If students have already answered the
    question, only its wording and explanation
    may be changed to protect old results.
    """

    question = db.session.get(
        Question,
        question_id,
    )

    if question is None:
        abort(404)

    worksheet = (
        get_teacher_worksheet_or_404(
            question.worksheet_id
        )
    )

    has_student_answers = (
        StudentAnswer.query
        .filter_by(
            question_id=question.id
        )
        .first()
        is not None
    )

    form = QuestionForm(
        obj=question
    )

    if request.method == "GET":
        form.choices_text.data = "\n".join(
            choice.choice_text
            for choice in question.choices
        )

    if form.validate_on_submit():
        question.question_text = (
            form.question_text.data.strip()
        )

        question.explanation = (
            form.explanation.data.strip()
            if form.explanation.data
            else None
        )

        if has_student_answers:
            db.session.commit()

            flash(
                (
                    "تم تعديل نص السؤال والشرح. "
                    "لم نغيّر الإجابة أو الدرجة "
                    "لوجود نتائج طلاب مرتبطة بالسؤال."
                ),
                "success",
            )

            return redirect(
                url_for(
                    "assessment.manage_questions",
                    worksheet_id=worksheet.id,
                )
            )

        question_type = (
            form.question_type.data
        )

        choices = [
            line.strip()
            for line
            in (
                form.choices_text.data
                or ""
            ).splitlines()
            if line.strip()
        ]

        correct_answer = (
            form.correct_answer_text.data
            or ""
        ).strip()

        if question_type == "multiple_choice":
            if len(choices) < 2:
                flash(
                    (
                        "سؤال الاختيار من متعدد "
                        "يحتاج خيارين على الأقل."
                    ),
                    "error",
                )

                return render_template(
                    "edit_question.html",
                    worksheet=worksheet,
                    question=question,
                    form=form,
                    has_student_answers=(
                        has_student_answers
                    ),
                )

            normalized_choices = {
                normalize_answer(choice)
                for choice in choices
            }

            if (
                normalize_answer(
                    correct_answer
                )
                not in normalized_choices
            ):
                flash(
                    (
                        "الإجابة الصحيحة يجب أن "
                        "تطابق أحد الخيارات تمامًا."
                    ),
                    "error",
                )

                return render_template(
                    "edit_question.html",
                    worksheet=worksheet,
                    question=question,
                    form=form,
                    has_student_answers=(
                        has_student_answers
                    ),
                )

        if question_type == "true_false":
            if normalize_answer(
                correct_answer
            ) not in {
                "صح",
                "خطأ",
            }:
                flash(
                    (
                        "اكتبي صح أو خطأ "
                        "كإجابة صحيحة."
                    ),
                    "error",
                )

                return render_template(
                    "edit_question.html",
                    worksheet=worksheet,
                    question=question,
                    form=form,
                    has_student_answers=(
                        has_student_answers
                    ),
                )

        if (
            question_type == "short_answer"
            and not correct_answer
        ):
            flash(
                (
                    "الإجابة الصحيحة مطلوبة "
                    "لسؤال الإجابة القصيرة."
                ),
                "error",
            )

            return render_template(
                "edit_question.html",
                worksheet=worksheet,
                question=question,
                form=form,
                has_student_answers=(
                    has_student_answers
                ),
            )

        question.question_type = (
            question_type
        )

        question.correct_answer_text = (
            correct_answer or None
        )

        question.points = (
            form.points.data
        )

        question.requires_manual_grading = (
            question_type == "essay"
        )

        for old_choice in list(
            question.choices
        ):
            db.session.delete(
                old_choice
            )

        db.session.flush()

        if question_type == "multiple_choice":
            for index, choice_text in enumerate(
                choices,
                start=1,
            ):
                db.session.add(
                    Choice(
                        question_id=question.id,
                        choice_text=choice_text,
                        is_correct=(
                            normalize_answer(
                                choice_text
                            )
                            == normalize_answer(
                                correct_answer
                            )
                        ),
                        order_index=index,
                    )
                )

        db.session.commit()

        flash(
            "تم تعديل السؤال بنجاح.",
            "success",
        )

        return redirect(
            url_for(
                "assessment.manage_questions",
                worksheet_id=worksheet.id,
            )
        )

    return render_template(
        "edit_question.html",
        worksheet=worksheet,
        question=question,
        form=form,
        has_student_answers=(
            has_student_answers
        ),
    )


def get_teacher_attempt_or_404(
    attempt_id,
):
    """
    Return a student attempt only when its
    worksheet belongs to the current teacher.

    Administrators may access all attempts.
    """

    attempt = db.session.get(
        WorksheetAttempt,
        attempt_id,
    )

    if attempt is None:
        abort(404)

    get_teacher_worksheet_or_404(
        attempt.worksheet_id
    )

    return attempt


@assessment_bp.route(
    "/teacher/attempts/"
    "<int:attempt_id>/grade",
    methods=["GET", "POST"],
)
@teacher_required
def grade_attempt(attempt_id):
    """
    Show the student's answers and allow
    the teacher to grade essay questions.
    """

    attempt = (
        get_teacher_attempt_or_404(
            attempt_id
        )
    )

    if not attempt.submitted_at:
        flash(
            (
                "الطالب لم يسلّم هذه "
                "المحاولة بعد."
            ),
            "info",
        )

        return redirect(
            url_for(
                "assessment.manage_questions",
                worksheet_id=(
                    attempt.worksheet_id
                ),
            )
        )

    if request.method == "POST":
        grading_errors = []

        for answer in attempt.answers:
            if not (
                answer
                .question
                .requires_manual_grading
            ):
                continue

            points_field = (
                f"points_{answer.id}"
            )

            feedback_field = (
                f"feedback_{answer.id}"
            )

            raw_points = (
                request.form.get(
                    points_field,
                    "0",
                )
            ).strip()

            try:
                awarded_points = float(
                    raw_points
                )
            except ValueError:
                grading_errors.append(
                    (
                        "درجة السؤال "
                        f"«{answer.question.question_text}» "
                        "غير صحيحة."
                    )
                )

                continue

            maximum_points = (
                answer.question.points
            )

            if (
                awarded_points < 0
                or awarded_points
                > maximum_points
            ):
                grading_errors.append(
                    (
                        "درجة السؤال "
                        f"«{answer.question.question_text}» "
                        "يجب أن تكون بين صفر "
                        f"و{maximum_points}."
                    )
                )

                continue

            answer.awarded_points = (
                awarded_points
            )

            answer.is_correct = (
                awarded_points
                >= maximum_points
            )

            answer.teacher_feedback = (
                request.form.get(
                    feedback_field,
                    "",
                ).strip()
                or None
            )

            answer.graded_at = utc_now()

        if grading_errors:
            for error in grading_errors:
                flash(
                    error,
                    "error",
                )

            return render_template(
                "grade_attempt.html",
                attempt=attempt,
            )

        calculate_attempt_result(
            attempt
        )

        db.session.commit()

        flash(
            (
                "تم حفظ التصحيح وتحديث "
                "نتيجة الطالب بنجاح."
            ),
            "success",
        )

        return redirect(
            url_for(
                "assessment.grade_attempt",
                attempt_id=attempt.id,
            )
        )

    return render_template(
        "grade_attempt.html",
        attempt=attempt,
    )


@assessment_bp.get(
    "/teacher/worksheets/"
    "<int:worksheet_id>/results"
)
@teacher_required
def worksheet_results(worksheet_id):
    """
    Display a separate results dashboard.

    Statistics use the latest submitted
    attempt for each student so a student
    is not counted more than once.
    """

    worksheet = (
        get_teacher_worksheet_or_404(
            worksheet_id
        )
    )

    submitted_attempts = (
        WorksheetAttempt.query
        .filter_by(
            worksheet_id=worksheet.id
        )
        .filter(
            WorksheetAttempt
            .submitted_at
            .isnot(None)
        )
        .order_by(
            WorksheetAttempt
            .submitted_at
            .desc()
        )
        .all()
    )

    attempts_count_by_student = {}

    for attempt in submitted_attempts:
        student_id = attempt.student_id

        attempts_count_by_student[
            student_id
        ] = (
            attempts_count_by_student.get(
                student_id,
                0,
            )
            + 1
        )

    latest_attempt_by_student = {}

    for attempt in submitted_attempts:
        if (
            attempt.student_id
            not in latest_attempt_by_student
        ):
            latest_attempt_by_student[
                attempt.student_id
            ] = attempt

    result_rows = []

    for attempt in (
        latest_attempt_by_student.values()
    ):
        pending_manual_grading = any(
            answer.is_correct is None
            for answer in attempt.answers
        )

        result_rows.append(
            {
                "attempt": attempt,
                "pending": (
                    pending_manual_grading
                ),
                "attempts_count": (
                    attempts_count_by_student[
                        attempt.student_id
                    ]
                ),
            }
        )

    result_rows.sort(
        key=lambda row: (
            row["attempt"].submitted_at
        ),
        reverse=True,
    )

    total_students = len(result_rows)

    pending_count = sum(
        1
        for row in result_rows
        if row["pending"]
    )

    passed_count = sum(
        1
        for row in result_rows
        if (
            not row["pending"]
            and row["attempt"].is_passed
        )
    )

    failed_count = sum(
        1
        for row in result_rows
        if (
            not row["pending"]
            and not row["attempt"].is_passed
        )
    )

    excellent_count = sum(
        1
        for row in result_rows
        if (
            not row["pending"]
            and 90
            <= row["attempt"].percentage
            < 100
        )
    )

    perfect_count = sum(
        1
        for row in result_rows
        if (
            not row["pending"]
            and row["attempt"].percentage
            >= 100
        )
    )

    graded_percentages = [
        row["attempt"].percentage
        for row in result_rows
        if not row["pending"]
    ]

    average_percentage = (
        sum(graded_percentages)
        / len(graded_percentages)
        if graded_percentages
        else 0.0
    )

    statistics = {
        "total_students": total_students,
        "passed_count": passed_count,
        "failed_count": failed_count,
        "pending_count": pending_count,
        "excellent_count": excellent_count,
        "perfect_count": perfect_count,
        "average_percentage": (
            average_percentage
        ),
    }

    return render_template(
        "worksheet_results.html",
        worksheet=worksheet,
        result_rows=result_rows,
        statistics=statistics,
    )
