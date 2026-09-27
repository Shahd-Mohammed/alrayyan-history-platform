from datetime import datetime, timezone

from alrayyan.extensions import db


def utc_now():
    return datetime.now(timezone.utc)


class ChallengeSession(db.Model):
    __tablename__ = "challenge_sessions"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lesson_id = db.Column(
        db.Integer,
        db.ForeignKey("lessons.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    concept = db.Column(db.String(250), nullable=True)
    mode = db.Column(
        db.String(30), nullable=False, default="lesson"
    )
    initial_difficulty = db.Column(
        db.String(20), nullable=False, default="medium"
    )
    current_difficulty = db.Column(
        db.String(20), nullable=False, default="medium"
    )
    total_rounds = db.Column(db.Integer, nullable=False, default=5)
    current_round = db.Column(db.Integer, nullable=False, default=1)
    score = db.Column(db.Integer, nullable=False, default=0)
    xp_earned = db.Column(db.Integer, nullable=False, default=0)
    combo = db.Column(db.Integer, nullable=False, default=0)
    best_combo = db.Column(db.Integer, nullable=False, default=0)
    correct_count = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(
        db.String(20), nullable=False, default="active", index=True
    )
    started_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    completed_at = db.Column(db.DateTime, nullable=True)

    student = db.relationship("User")
    lesson = db.relationship("Lesson")
    questions = db.relationship(
        "ChallengeQuestion",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChallengeQuestion.round_number",
    )


class ChallengeQuestion(db.Model):
    __tablename__ = "challenge_questions"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.Integer,
        db.ForeignKey("challenge_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    round_number = db.Column(db.Integer, nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    question_type = db.Column(
        db.String(30), nullable=False, default="multiple_choice"
    )
    options_json = db.Column(db.JSON, nullable=False)
    correct_option_index = db.Column(db.Integer, nullable=False)
    explanation = db.Column(db.Text, nullable=False)
    hint_one = db.Column(db.Text, nullable=False)
    hint_two = db.Column(db.Text, nullable=False)
    difficulty = db.Column(db.String(20), nullable=False)
    concept = db.Column(db.String(250), nullable=True)
    generation_model = db.Column(db.String(150), nullable=True)
    prompt_version = db.Column(
        db.String(30), nullable=False, default="challenge-v1"
    )
    hints_used = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    session = db.relationship(
        "ChallengeSession", back_populates="questions"
    )
    answer = db.relationship(
        "ChallengeAnswer",
        back_populates="question",
        cascade="all, delete-orphan",
        uselist=False,
    )
    source_links = db.relationship(
        "ChallengeQuestionSource",
        back_populates="question",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        db.UniqueConstraint(
            "session_id",
            "round_number",
            name="uq_challenge_session_round",
        ),
    )


class ChallengeQuestionSource(db.Model):
    __tablename__ = "challenge_question_sources"

    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(
        db.Integer,
        db.ForeignKey("challenge_questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_id = db.Column(
        db.Integer,
        db.ForeignKey("content_chunks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    question = db.relationship(
        "ChallengeQuestion", back_populates="source_links"
    )
    chunk = db.relationship("ContentChunk")

    __table_args__ = (
        db.UniqueConstraint(
            "question_id",
            "chunk_id",
            name="uq_challenge_question_chunk",
        ),
    )


class ChallengeAnswer(db.Model):
    __tablename__ = "challenge_answers"

    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(
        db.Integer,
        db.ForeignKey("challenge_questions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    student_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    selected_option_index = db.Column(db.Integer, nullable=False)
    is_correct = db.Column(db.Boolean, nullable=False)
    evaluation_status = db.Column(db.String(30), nullable=False)
    feedback = db.Column(db.Text, nullable=False)
    hints_used = db.Column(db.Integer, nullable=False, default=0)
    score_awarded = db.Column(db.Integer, nullable=False, default=0)
    xp_awarded = db.Column(db.Integer, nullable=False, default=0)
    response_time_seconds = db.Column(db.Integer, nullable=True)
    answered_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    question = db.relationship(
        "ChallengeQuestion", back_populates="answer"
    )
    student = db.relationship("User")


class XPTransaction(db.Model):
    __tablename__ = "xp_transactions"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(100), nullable=False)
    source_type = db.Column(db.String(40), nullable=False)
    source_id = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    student = db.relationship("User")

    __table_args__ = (
        db.UniqueConstraint(
            "student_id",
            "reason",
            "source_type",
            "source_id",
            name="uq_xp_award_source",
        ),
    )
