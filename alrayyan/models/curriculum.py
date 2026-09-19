from datetime import datetime, timezone

from alrayyan.extensions import db


class Curriculum(db.Model):
    __tablename__ = "curricula"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    subject = db.Column(db.String(100), nullable=False)
    grade = db.Column(db.String(50), nullable=False)
    semester = db.Column(db.String(50), nullable=False)
    academic_year = db.Column(db.String(30))
    version = db.Column(db.String(50), default="1.0")
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    units = db.relationship(
        "Unit",
        back_populates="curriculum",
        cascade="all, delete-orphan",
        order_by="Unit.order_index",
    )


class Unit(db.Model):
    __tablename__ = "units"

    id = db.Column(db.Integer, primary_key=True)
    curriculum_id = db.Column(
        db.Integer,
        db.ForeignKey("curricula.id", ondelete="CASCADE"),
        nullable=False,
    )
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    order_index = db.Column(db.Integer, nullable=False, default=1)

    curriculum = db.relationship(
        "Curriculum",
        back_populates="units",
    )

    lessons = db.relationship(
        "Lesson",
        back_populates="unit",
        cascade="all, delete-orphan",
        order_by="Lesson.order_index",
    )


class Lesson(db.Model):
    __tablename__ = "lessons"

    id = db.Column(db.Integer, primary_key=True)
    unit_id = db.Column(
        db.Integer,
        db.ForeignKey("units.id", ondelete="CASCADE"),
        nullable=False,
    )
    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(220), unique=True, nullable=False)
    summary = db.Column(db.Text)
    learning_objectives = db.Column(db.Text)
    order_index = db.Column(db.Integer, nullable=False, default=1)
    is_published = db.Column(db.Boolean, default=False, nullable=False)

    unit = db.relationship(
        "Unit",
        back_populates="lessons",
    )

    sources = db.relationship(
        "SourceDocument",
        back_populates="lesson",
        cascade="all, delete-orphan",
    )


class SourceDocument(db.Model):
    __tablename__ = "source_documents"

    id = db.Column(db.Integer, primary_key=True)
    lesson_id = db.Column(
        db.Integer,
        db.ForeignKey("lessons.id", ondelete="CASCADE"),
        nullable=False,
    )
    title = db.Column(db.String(250), nullable=False)
    source_type = db.Column(db.String(50), nullable=False)
    original_filename = db.Column(db.String(255))
    stored_path = db.Column(db.String(500))
    page_count = db.Column(db.Integer)
    checksum = db.Column(db.String(64), index=True)
    academic_year = db.Column(db.String(30))
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    lesson = db.relationship(
        "Lesson",
        back_populates="sources",
    )

    chunks = db.relationship(
        "ContentChunk",
        back_populates="source",
        cascade="all, delete-orphan",
        order_by="ContentChunk.chunk_index",
    )


class ContentChunk(db.Model):
    __tablename__ = "content_chunks"

    id = db.Column(db.Integer, primary_key=True)
    source_id = db.Column(
        db.Integer,
        db.ForeignKey("source_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    page_number = db.Column(db.Integer)
    chunk_index = db.Column(db.Integer, nullable=False)
    text = db.Column(db.Text, nullable=False)
    embedding = db.Column(db.Text)
    token_count = db.Column(db.Integer)

    source = db.relationship(
        "SourceDocument",
        back_populates="chunks",
    )

    __table_args__ = (
        db.UniqueConstraint(
            "source_id",
            "chunk_index",
            name="uq_source_chunk",
        ),
    )