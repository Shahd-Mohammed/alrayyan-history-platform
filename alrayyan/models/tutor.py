from datetime import datetime, timezone

from alrayyan.extensions import db


def utc_now():
    return datetime.now(timezone.utc)


class TutorConversation(db.Model):
    __tablename__ = "tutor_conversations"

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
    title = db.Column(db.String(180), nullable=False, default="محادثة تعليمية")
    difficulty = db.Column(db.String(20), nullable=False, default="adaptive")
    current_concept = db.Column(db.String(250), nullable=True)
    tutor_state = db.Column(db.String(30), nullable=False, default="diagnose")
    summary = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="active", index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    student = db.relationship("User")
    lesson = db.relationship("Lesson")
    messages = db.relationship(
        "TutorMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="TutorMessage.created_at",
    )


class TutorMessage(db.Model):
    __tablename__ = "tutor_messages"

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(
        db.Integer,
        db.ForeignKey("tutor_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, nullable=False)
    action = db.Column(db.String(40), nullable=True)
    evaluation = db.Column(db.String(30), nullable=True)
    concept = db.Column(db.String(250), nullable=True)
    mastery_delta = db.Column(db.Integer, nullable=False, default=0)
    model = db.Column(db.String(150), nullable=True)
    prompt_version = db.Column(db.String(30), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    conversation = db.relationship(
        "TutorConversation", back_populates="messages"
    )
    source_links = db.relationship(
        "TutorMessageSource",
        back_populates="message",
        cascade="all, delete-orphan",
    )


class TutorMessageSource(db.Model):
    __tablename__ = "tutor_message_sources"

    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(
        db.Integer,
        db.ForeignKey("tutor_messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_id = db.Column(
        db.Integer,
        db.ForeignKey("content_chunks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    message = db.relationship("TutorMessage", back_populates="source_links")
    chunk = db.relationship("ContentChunk")

    __table_args__ = (
        db.UniqueConstraint(
            "message_id", "chunk_id", name="uq_tutor_message_chunk"
        ),
    )


class ConceptMastery(db.Model):
    __tablename__ = "concept_masteries"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lesson_id = db.Column(
        db.Integer,
        db.ForeignKey("lessons.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    concept = db.Column(db.String(250), nullable=False)
    mastery_score = db.Column(db.Integer, nullable=False, default=50)
    correct_count = db.Column(db.Integer, nullable=False, default=0)
    partial_count = db.Column(db.Integer, nullable=False, default=0)
    incorrect_count = db.Column(db.Integer, nullable=False, default=0)
    last_reviewed_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    student = db.relationship("User")
    lesson = db.relationship("Lesson")
    __table_args__ = (
        db.UniqueConstraint(
            "student_id", "lesson_id", "concept",
            name="uq_student_lesson_concept_mastery",
        ),
    )


class LearningPlanItem(db.Model):
    __tablename__ = "learning_plan_items"

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
    item_type = db.Column(db.String(40), nullable=False)
    title = db.Column(db.String(250), nullable=False)
    description = db.Column(db.Text, nullable=False)
    priority = db.Column(db.Integer, nullable=False, default=50)
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    completed_at = db.Column(db.DateTime, nullable=True)
    verification_score = db.Column(db.Integer, nullable=True)
    verified_at = db.Column(db.DateTime, nullable=True)

    student = db.relationship("User")
    lesson = db.relationship("Lesson")
