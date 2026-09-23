from datetime import datetime, timezone

from alrayyan.extensions import db


class Worksheet(db.Model):
    __tablename__ = "worksheets"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    lesson_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "lessons.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    created_by_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    title = db.Column(
        db.String(250),
        nullable=False,
    )

    description = db.Column(
        db.Text,
        nullable=True,
    )

    instructions = db.Column(
        db.Text,
        nullable=True,
    )

    creation_method = db.Column(
        db.String(30),
        nullable=False,
        default="manual",
        index=True,
    )

    difficulty_level = db.Column(
        db.String(30),
        nullable=False,
        default="medium",
    )

    publication_status = db.Column(
        db.String(30),
        nullable=False,
        default="draft",
        index=True,
    )

    allow_download = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
    )

    is_ai_generated = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
    )

    time_limit_minutes = db.Column(
        db.Integer,
        nullable=True,
    )

    passing_score = db.Column(
        db.Float,
        nullable=False,
        default=50.0,
    )

    allow_multiple_attempts = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
    )
    max_attempts = db.Column(
    db.Integer,
    nullable=False,
    default=3,
    server_default="3",
    )

    show_answers_after_submit = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
    )

    is_published = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        index=True,
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    lesson = db.relationship(
        "Lesson",
        back_populates="worksheets",
    )

    questions = db.relationship(
        "Question",
        back_populates="worksheet",
        cascade="all, delete-orphan",
        order_by="Question.order_index",
    )

    attempts = db.relationship(
        "WorksheetAttempt",
        back_populates="worksheet",
        cascade="all, delete-orphan",
    )

    created_by = db.relationship(
        "User",
        foreign_keys=[created_by_id],
    )

    attachments = db.relationship(
        "WorksheetAttachment",
        back_populates="worksheet",
        cascade="all, delete-orphan",
        order_by="WorksheetAttachment.created_at",
    )

    def total_points(self):
        return sum(
            question.points
            for question in self.questions
        )


class Question(db.Model):
    __tablename__ = "questions"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    worksheet_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "worksheets.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    question_text = db.Column(
        db.Text,
        nullable=False,
    )

    question_type = db.Column(
        db.String(40),
        nullable=False,
        default="multiple_choice",
    )

    interaction_config = db.Column(
        db.Text,
        nullable=True,
    )

    requires_manual_grading = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
    )
    correct_answer_text = db.Column(
        db.Text,
        nullable=True,
    )

    explanation = db.Column(
        db.Text,
        nullable=True,
    )

    points = db.Column(
        db.Float,
        nullable=False,
        default=1.0,
    )

    order_index = db.Column(
        db.Integer,
        nullable=False,
        default=1,
    )

    worksheet = db.relationship(
        "Worksheet",
        back_populates="questions",
    )

    choices = db.relationship(
        "Choice",
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="Choice.order_index",
    )

    student_answers = db.relationship(
        "StudentAnswer",
        back_populates="question",
    )

    __table_args__ = (
        db.UniqueConstraint(
            "worksheet_id",
            "order_index",
            name="uq_worksheet_question_order",
        ),
    )


class Choice(db.Model):
    __tablename__ = "choices"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    question_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "questions.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    choice_text = db.Column(
        db.Text,
        nullable=False,
    )

    is_correct = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
    )

    order_index = db.Column(
        db.Integer,
        nullable=False,
        default=1,
    )

    question = db.relationship(
        "Question",
        back_populates="choices",
    )

    student_answers = db.relationship(
        "StudentAnswer",
        back_populates="selected_choice",
    )

    __table_args__ = (
        db.UniqueConstraint(
            "question_id",
            "order_index",
            name="uq_question_choice_order",
        ),
    )


class WorksheetAttempt(db.Model):
    __tablename__ = "worksheet_attempts"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    worksheet_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "worksheets.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    student_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    started_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    submitted_at = db.Column(
        db.DateTime,
        nullable=True,
    )

    score = db.Column(
        db.Float,
        nullable=False,
        default=0.0,
    )

    max_score = db.Column(
        db.Float,
        nullable=False,
        default=0.0,
    )

    percentage = db.Column(
        db.Float,
        nullable=False,
        default=0.0,
    )

    is_passed = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
    )

    worksheet = db.relationship(
        "Worksheet",
        back_populates="attempts",
    )

    student = db.relationship(
        "User",
        back_populates="worksheet_attempts",
    )

    answers = db.relationship(
        "StudentAnswer",
        back_populates="attempt",
        cascade="all, delete-orphan",
    )


class StudentAnswer(db.Model):
    __tablename__ = "student_answers"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    attempt_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "worksheet_attempts.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    question_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "questions.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    selected_choice_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "choices.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    answer_text = db.Column(
        db.Text,
        nullable=True,
    )

    answer_data = db.Column(
        db.Text,
        nullable=True,
    )

    teacher_feedback = db.Column(
        db.Text,
        nullable=True,
    )

    graded_at = db.Column(
        db.DateTime,
        nullable=True,
    )
    is_correct = db.Column(
        db.Boolean,
        nullable=True,
    )

    awarded_points = db.Column(
        db.Float,
        nullable=False,
        default=0.0,
    )

    answered_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    attempt = db.relationship(
        "WorksheetAttempt",
        back_populates="answers",
    )

    question = db.relationship(
        "Question",
        back_populates="student_answers",
    )

    selected_choice = db.relationship(
        "Choice",
        back_populates="student_answers",
    )

    __table_args__ = (
        db.UniqueConstraint(
            "attempt_id",
            "question_id",
            name="uq_attempt_question_answer",
        ),
    )

class WorksheetAttachment(db.Model):
    __tablename__ = "worksheet_attachments"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    worksheet_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "worksheets.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    attachment_type = db.Column(
        db.String(30),
        nullable=False,
        default="worksheet",
    )

    original_filename = db.Column(
        db.String(255),
        nullable=False,
    )

    stored_filename = db.Column(
        db.String(255),
        nullable=False,
        unique=True,
    )

    storage_path = db.Column(
        db.String(500),
        nullable=False,
    )

    file_extension = db.Column(
        db.String(20),
        nullable=False,
    )

    mime_type = db.Column(
        db.String(150),
        nullable=True,
    )

    file_size = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    worksheet = db.relationship(
        "Worksheet",
        back_populates="attachments",
    )