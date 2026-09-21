from datetime import datetime, timezone

from alrayyan.extensions import db


class HistoricalDate(db.Model):
    __tablename__ = "historical_dates"

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

    date_label = db.Column(
        db.String(100),
        nullable=False,
    )

    sort_year = db.Column(
        db.Integer,
        nullable=True,
        index=True,
    )

    event_title = db.Column(
        db.String(250),
        nullable=False,
    )

    event_description = db.Column(
        db.Text,
        nullable=True,
    )

    memory_hint = db.Column(
        db.Text,
        nullable=True,
    )

    importance_level = db.Column(
        db.Integer,
        nullable=False,
        default=1,
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

    lesson = db.relationship(
        "Lesson",
        back_populates="historical_dates",
    )

    reviews = db.relationship(
        "DateReview",
        back_populates="historical_date",
        cascade="all, delete-orphan",
    )


class DateReview(db.Model):
    __tablename__ = "date_reviews"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    historical_date_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "historical_dates.id",
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

    repetitions = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    interval_days = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    easiness_factor = db.Column(
        db.Float,
        nullable=False,
        default=2.5,
    )

    last_result = db.Column(
        db.Integer,
        nullable=True,
    )

    last_reviewed_at = db.Column(
        db.DateTime,
        nullable=True,
    )

    next_review_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    historical_date = db.relationship(
        "HistoricalDate",
        back_populates="reviews",
    )

    student = db.relationship(
        "User",
        back_populates="date_reviews",
    )

    __table_args__ = (
        db.UniqueConstraint(
            "historical_date_id",
            "student_id",
            name="uq_student_historical_date",
        ),
    )