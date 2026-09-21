from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import (
    check_password_hash,
    generate_password_hash,
)

from alrayyan.extensions import db


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    full_name = db.Column(
        db.String(150),
        nullable=False,
    )

    email = db.Column(
        db.String(255),
        nullable=False,
        unique=True,
        index=True,
    )

    password_hash = db.Column(
        db.String(255),
        nullable=False,
    )

    role = db.Column(
        db.String(30),
        nullable=False,
        default="student",
        index=True,
    )

    points = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    level = db.Column(
        db.Integer,
        nullable=False,
        default=1,
    )

    is_active_account = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    worksheet_attempts = db.relationship(
        "WorksheetAttempt",
        back_populates="student",
        cascade="all, delete-orphan",
    )

    date_reviews = db.relationship(
        "DateReview",
        back_populates="student",
        cascade="all, delete-orphan",
    )

    def set_password(self, password):
        if not password or len(password) < 8:
            raise ValueError(
                "Password must contain at least 8 characters."
            )

        self.password_hash = generate_password_hash(
            password
        )

    def check_password(self, password):
        return check_password_hash(
            self.password_hash,
            password,
        )

    @property
    def is_active(self):
        return self.is_active_account

    def __repr__(self):
        return (
            f"<User id={self.id} "
            f"email={self.email!r} "
            f"role={self.role!r}>"
        )