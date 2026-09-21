from datetime import datetime, timezone

from alrayyan.extensions import db


class Curriculum(db.Model):
    __tablename__ = "curricula"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    subject = db.Column(db.String(100), nullable=False)
    grade = db.Column(db.String(50), nullable=False)
    semester = db.Column(db.String(50), nullable=False)
    academic_year = db.Column(db.String(30), nullable=False)
    version = db.Column(
        db.String(50),
        nullable=False,
        default="1.0",
    )
    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
    )
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    units = db.relationship(
        "Unit",
        back_populates="curriculum",
        cascade="all, delete-orphan",
        order_by="Unit.order_index",
    )

    sources = db.relationship(
        "SourceDocument",
        back_populates="curriculum",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        db.UniqueConstraint(
            "grade",
            "semester",
            "academic_year",
            "version",
            name="uq_curriculum_version",
        ),
    )


class Unit(db.Model):
    __tablename__ = "units"

    id = db.Column(db.Integer, primary_key=True)

    curriculum_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "curricula.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    title = db.Column(
        db.String(200),
        nullable=False,
    )
    description = db.Column(db.Text)
    order_index = db.Column(
        db.Integer,
        nullable=False,
        default=1,
    )

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

    __table_args__ = (
        db.UniqueConstraint(
            "curriculum_id",
            "order_index",
            name="uq_curriculum_unit_order",
        ),
    )


class Lesson(db.Model):
    __tablename__ = "lessons"

    id = db.Column(db.Integer, primary_key=True)

    unit_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "units.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    title = db.Column(
        db.String(250),
        nullable=False,
    )
    slug = db.Column(
        db.String(250),
        unique=True,
        nullable=False,
    )
    summary = db.Column(db.Text)
    learning_objectives = db.Column(db.Text)
    order_index = db.Column(
        db.Integer,
        nullable=False,
        default=1,
    )
    is_published = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
    )

    unit = db.relationship(
        "Unit",
        back_populates="lessons",
    )

    sources = db.relationship(
        "SourceDocument",
        back_populates="lesson",
    )

    chunks = db.relationship(
        "ContentChunk",
        back_populates="lesson",
    )
    
    worksheets = db.relationship(
        "Worksheet",
        back_populates="lesson",
        cascade="all, delete-orphan",
    )

    historical_dates = db.relationship(
        "HistoricalDate",
        back_populates="lesson",
        cascade="all, delete-orphan",
        order_by="HistoricalDate.sort_year",
    )

    __table_args__ = (
        db.UniqueConstraint(
            "unit_id",
            "order_index",
            name="uq_unit_lesson_order",
        ),
    )


class SourceDocument(db.Model):
    __tablename__ = "source_documents"

    id = db.Column(db.Integer, primary_key=True)

    curriculum_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "curricula.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    lesson_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "lessons.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    title = db.Column(
        db.String(250),
        nullable=False,
    )
    source_type = db.Column(
        db.String(50),
        nullable=False,
    )
    original_filename = db.Column(db.String(255))
    stored_path = db.Column(db.String(500))
    page_count = db.Column(db.Integer)
    checksum = db.Column(
        db.String(64),
        nullable=False,
        index=True,
    )
    academic_year = db.Column(db.String(30))

    priority = db.Column(
        db.Integer,
        nullable=False,
        default=100,
    )
    is_primary = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
    )
    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    curriculum = db.relationship(
        "Curriculum",
        back_populates="sources",
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

    __table_args__ = (
        db.UniqueConstraint(
            "curriculum_id",
            "checksum",
            name="uq_curriculum_source_checksum",
        ),
    )


class ContentChunk(db.Model):
    __tablename__ = "content_chunks"

    id = db.Column(db.Integer, primary_key=True)

    source_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "source_documents.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    lesson_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "lessons.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    page_number = db.Column(db.Integer)
    chunk_index = db.Column(
        db.Integer,
        nullable=False,
    )
    text = db.Column(
        db.Text,
        nullable=False,
    )
    text_hash = db.Column(
        db.String(64),
        nullable=False,
        index=True,
    )
    embedding = db.Column(db.Text)

    embedding_model = db.Column(
        db.String(150),
        nullable=True,
    )

    embedding_dimensions = db.Column(
        db.Integer,
        nullable=True,
    )

    embedded_at = db.Column(
        db.DateTime,
        nullable=True,
    )

    token_count = db.Column(db.Integer)

    source = db.relationship(
        "SourceDocument",
        back_populates="chunks",
    )

    lesson = db.relationship(
        "Lesson",
        back_populates="chunks",
    )

    __table_args__ = (
        db.UniqueConstraint(
            "source_id",
            "chunk_index",
            name="uq_source_chunk",
        ),
    )