import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from alrayyan.extensions import db


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class PlatformSettings(db.Model):
    __tablename__ = "platform_settings"
    id = db.Column(db.Integer, primary_key=True)
    platform_name = db.Column(db.String(150), nullable=False, default="منصة الريان التعليمية")
    tagline = db.Column(db.String(250), nullable=False, default="تعلّم ذكي، ممارسة هادفة، وتقدّم يمكن قياسه")
    whatsapp_url = db.Column(db.String(500))
    support_email = db.Column(db.String(255))
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    @classmethod
    def get_or_create(cls):
        row = cls.query.first()
        if row is None:
            row = cls()
            db.session.add(row)
            db.session.commit()
        return row


class Classroom(db.Model):
    __tablename__ = "classrooms"
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    grade = db.Column(db.String(50), nullable=False)
    academic_year = db.Column(db.String(30), nullable=False)
    whatsapp_url = db.Column(db.String(500))
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    teacher = db.relationship("User", foreign_keys=[teacher_id])
    enrollments = db.relationship("ClassEnrollment", back_populates="classroom", cascade="all, delete-orphan")
    __table_args__ = (db.UniqueConstraint("teacher_id", "name", "academic_year", name="uq_teacher_classroom_year"),)


class ClassEnrollment(db.Model):
    __tablename__ = "class_enrollments"
    id = db.Column(db.Integer, primary_key=True)
    classroom_id = db.Column(db.Integer, db.ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    joined_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    classroom = db.relationship("Classroom", back_populates="enrollments")
    student = db.relationship("User", foreign_keys=[student_id])
    __table_args__ = (db.UniqueConstraint("classroom_id", "student_id", name="uq_classroom_student"),)


class StudentInvitation(db.Model):
    __tablename__ = "student_invitations"
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    classroom_id = db.Column(db.Integer, db.ForeignKey("classrooms.id", ondelete="SET NULL"), index=True)
    email = db.Column(db.String(255), nullable=False, index=True)
    token_hash = db.Column(db.String(64), nullable=False, unique=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    accepted_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    teacher = db.relationship("User", foreign_keys=[teacher_id])
    classroom = db.relationship("Classroom")

    @classmethod
    def create(cls, teacher_id, email, classroom_id=None, valid_days=7):
        raw_token = secrets.token_urlsafe(32)
        row = cls(teacher_id=teacher_id, classroom_id=classroom_id, email=email.strip().lower(), token_hash=hashlib.sha256(raw_token.encode()).hexdigest(), expires_at=utc_now() + timedelta(days=valid_days))
        return row, raw_token

    @classmethod
    def find_valid(cls, raw_token):
        if not raw_token:
            return None
        digest = hashlib.sha256(raw_token.encode()).hexdigest()
        return cls.query.filter_by(token_hash=digest, accepted_at=None).filter(cls.expires_at > utc_now()).first()


class LearningResource(db.Model):
    __tablename__ = "learning_resources"
    id = db.Column(db.Integer, primary_key=True)
    lesson_id = db.Column(db.Integer, db.ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), index=True)
    title = db.Column(db.String(250), nullable=False)
    resource_type = db.Column(db.String(40), nullable=False, index=True)
    creation_method = db.Column(db.String(30), nullable=False, default="upload")
    description = db.Column(db.Text)
    original_filename = db.Column(db.String(255))
    stored_path = db.Column(db.String(500))
    mime_type = db.Column(db.String(150))
    allow_download = db.Column(db.Boolean, nullable=False, default=True)
    publication_status = db.Column(db.String(30), nullable=False, default="draft", index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    lesson = db.relationship("Lesson")
    created_by = db.relationship("User", foreign_keys=[created_by_id])


class ConceptMap(db.Model):
    __tablename__ = "concept_maps"
    id = db.Column(db.Integer, primary_key=True)
    lesson_id = db.Column(db.Integer, db.ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), index=True)
    title = db.Column(db.String(250), nullable=False)
    map_type = db.Column(db.String(40), nullable=False, default="concept")
    creation_method = db.Column(db.String(30), nullable=False, default="manual")
    publication_status = db.Column(db.String(30), nullable=False, default="draft")
    original_filename = db.Column(db.String(255))
    stored_path = db.Column(db.String(500))
    mime_type = db.Column(db.String(150))
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    lesson = db.relationship("Lesson")
    nodes = db.relationship("ConceptMapNode", back_populates="concept_map", cascade="all, delete-orphan")
    edges = db.relationship("ConceptMapEdge", back_populates="concept_map", cascade="all, delete-orphan")


class ConceptMapNode(db.Model):
    __tablename__ = "concept_map_nodes"
    id = db.Column(db.Integer, primary_key=True)
    concept_map_id = db.Column(db.Integer, db.ForeignKey("concept_maps.id", ondelete="CASCADE"), nullable=False, index=True)
    label = db.Column(db.String(250), nullable=False)
    description = db.Column(db.Text)
    position_x = db.Column(db.Float, nullable=False, default=0)
    position_y = db.Column(db.Float, nullable=False, default=0)
    concept_map = db.relationship("ConceptMap", back_populates="nodes")


class ConceptMapEdge(db.Model):
    __tablename__ = "concept_map_edges"
    id = db.Column(db.Integer, primary_key=True)
    concept_map_id = db.Column(db.Integer, db.ForeignKey("concept_maps.id", ondelete="CASCADE"), nullable=False, index=True)
    source_node_id = db.Column(db.Integer, db.ForeignKey("concept_map_nodes.id", ondelete="CASCADE"), nullable=False)
    target_node_id = db.Column(db.Integer, db.ForeignKey("concept_map_nodes.id", ondelete="CASCADE"), nullable=False)
    label = db.Column(db.String(150))
    concept_map = db.relationship("ConceptMap", back_populates="edges")
    source_node = db.relationship("ConceptMapNode", foreign_keys=[source_node_id])
    target_node = db.relationship("ConceptMapNode", foreign_keys=[target_node_id])


class HistoricalCharacter(db.Model):
    __tablename__ = "historical_characters"
    id = db.Column(db.Integer, primary_key=True)
    lesson_id = db.Column(db.Integer, db.ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), index=True)
    name = db.Column(db.String(200), nullable=False)
    period = db.Column(db.String(150))
    summary = db.Column(db.Text, nullable=False)
    key_events = db.Column(db.Text)
    source_notes = db.Column(db.Text)
    clues = db.Column(db.Text)
    publication_status = db.Column(db.String(30), nullable=False, default="draft")
    is_ai_generated = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    lesson = db.relationship("Lesson")
    __table_args__ = (db.UniqueConstraint("lesson_id", "name", name="uq_lesson_character"),)


class CharacterAttempt(db.Model):
    __tablename__ = "character_attempts"
    id = db.Column(db.Integer, primary_key=True)
    character_id = db.Column(db.Integer, db.ForeignKey("historical_characters.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    answer_text = db.Column(db.String(250), nullable=False)
    is_correct = db.Column(db.Boolean, nullable=False)
    hints_used = db.Column(db.Integer, nullable=False, default=0)
    xp_awarded = db.Column(db.Integer, nullable=False, default=0)
    attempted_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    character = db.relationship("HistoricalCharacter")
    student = db.relationship("User")
    __table_args__ = (db.UniqueConstraint("character_id", "student_id", name="uq_character_student_attempt"),)


class HonorBoardEntry(db.Model):
    __tablename__ = "honor_board_entries"
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    category = db.Column(db.String(50), nullable=False)
    note = db.Column(db.String(300))
    period_label = db.Column(db.String(100))
    is_manual = db.Column(db.Boolean, nullable=False, default=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    teacher = db.relationship("User", foreign_keys=[teacher_id])
    student = db.relationship("User", foreign_keys=[student_id])
