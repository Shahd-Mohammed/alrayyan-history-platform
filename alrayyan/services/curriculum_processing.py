import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from flask import current_app

from alrayyan.extensions import db
from alrayyan.models import ContentChunk, Lesson, Unit
from alrayyan.services.document_reader import extract_docx, extract_pdf
from alrayyan.services.embeddings import generate_embeddings, get_embedding_settings
from alrayyan.services.text_processing import chunk_text, create_text_hash


def _prepare_curriculum_orders(curriculum):
    """Move existing orders to unique temporary values before reordering."""
    # Use database IDs so every temporary order is unique even while
    # SQLAlchemy updates rows one by one under the UNIQUE constraints.
    for unit in curriculum.units:
        unit.order_index = -(100000 + unit.id)

        for lesson in unit.lessons:
            lesson.order_index = -(200000 + lesson.id)

    db.session.flush()


def _get_or_create_unit(curriculum, title, order_index):
    title = (title or "").strip() or "الوحدة الأولى"

    unit = Unit.query.filter_by(
        curriculum_id=curriculum.id,
        title=title,
    ).first()
    if unit:
        unit.order_index = order_index
        return unit

    unit = Unit(
        curriculum_id=curriculum.id,
        title=title[:200],
        order_index=order_index,
    )
    db.session.add(unit)
    db.session.flush()
    return unit


def _get_or_create_lesson(unit, title, order_index):
    title = (title or "").strip() or "محتوى المنهج"

    lesson = Lesson.query.filter_by(
        unit_id=unit.id,
        title=title,
    ).first()
    if lesson:
        lesson.order_index = order_index
        return lesson

    lesson = Lesson(
        unit_id=unit.id,
        title=title[:250],
        slug=f"lesson-{uuid4().hex[:16]}",
        order_index=order_index,
        is_published=True,
    )
    db.session.add(lesson)
    db.session.flush()
    return lesson


def process_source_document(
    source,
    fallback_unit_title=None,
    fallback_lesson_title=None,
):
    """Extract, section, chunk, and embed a curriculum source."""
    if not source.stored_path:
        raise ValueError("ملف المصدر غير موجود")

    upload_root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    file_path = (upload_root / source.stored_path).resolve()
    if not file_path.is_relative_to(upload_root) or not file_path.is_file():
        raise ValueError("ملف المصدر غير موجود على الخادم")

    extension = file_path.suffix.lower()
    extracted = (
        extract_pdf(file_path)
        if extension == ".pdf"
        else extract_docx(file_path)
        if extension == ".docx"
        else None
    )
    if extracted is None:
        raise ValueError("صيغة ملف المصدر غير مدعومة")

    sections = extracted.get("sections") or [{
        "unit_title": fallback_unit_title,
        "lesson_title": fallback_lesson_title,
        "text": extracted.get("text", ""),
    }]

    resolved_sections = []
    _prepare_curriculum_orders(source.curriculum)
    unit_orders = {}
    lesson_orders = {}
    for section in sections:
        text = (section.get("text") or "").strip()
        if not text:
            continue

        unit_title = section.get("unit_title") or fallback_unit_title
        unit_key = (unit_title or "الوحدة الأولى").strip()
        unit_orders.setdefault(unit_key, len(unit_orders) + 1)
        unit = _get_or_create_unit(
            source.curriculum,
            unit_key,
            unit_orders[unit_key],
        )

        lesson_title = section.get("lesson_title") or fallback_lesson_title
        lesson_key = (lesson_title or "محتوى المنهج").strip()
        lesson_key_full = (unit.id, lesson_key)
        lesson_orders.setdefault(lesson_key_full, len([key for key in lesson_orders if key[0] == unit.id]) + 1)
        lesson = _get_or_create_lesson(
            unit,
            lesson_key,
            lesson_orders[lesson_key_full],
        )
        resolved_sections.append({
            "unit_title": unit.title,
            "lesson_title": lesson.title,
            "lesson_id": lesson.id,
            "text": text,
        })

    if not resolved_sections:
        raise ValueError("لم نستطع استخراج نص؛ قد يكون الملف فارغًا أو عبارة عن صور ويحتاج OCR")

    chunk_data = []
    index = 0
    for section in resolved_sections:
        context_prefix = f"{section['unit_title']}\n{section['lesson_title']}\n"
        for text in chunk_text(section["text"]):
            contextual_text = f"{context_prefix}{text}".strip()
            chunk_data.append({
                "lesson_id": section["lesson_id"],
                "page_number": None,
                "chunk_index": index,
                "text": contextual_text,
                "text_hash": create_text_hash(contextual_text),
                "token_count": len(contextual_text.split()),
            })
            index += 1

    if not chunk_data:
        raise ValueError("لم نستطع تقسيم محتوى الملف إلى مقاطع")

    embedding_settings = get_embedding_settings()
    vectors = []
    batch_size = current_app.config.get("EMBEDDING_BATCH_SIZE", 20)
    for start in range(0, len(chunk_data), batch_size):
        batch = chunk_data[start:start + batch_size]
        vectors.extend(generate_embeddings([item["text"] for item in batch]))

    embedded_at = datetime.now(timezone.utc).replace(tzinfo=None)

    ContentChunk.query.filter_by(
        source_id=source.id,
    ).delete(synchronize_session=False)

    for item, vector in zip(chunk_data, vectors):
        db.session.add(ContentChunk(
            source_id=source.id,
            lesson_id=item["lesson_id"],
            page_number=item["page_number"],
            chunk_index=item["chunk_index"],
            text=item["text"],
            text_hash=item["text_hash"],
            token_count=item["token_count"],
            embedding=json.dumps(vector),
            embedding_model=embedding_settings["model"],
            embedding_dimensions=len(vector),
            embedded_at=embedded_at,
        ))

    source.page_count = extracted.get("page_count")

    # Two-phase renumbering is required because (curriculum_id, order_index)
    # and (unit_id, order_index) are UNIQUE constraints. Directly swapping
    # 1 <-> 2 can fail even when the final order is valid.
    units_sorted = sorted(
        source.curriculum.units,
        key=lambda item: (
            item.order_index if item.order_index > 0 else 9999,
            item.id,
        ),
    )

    # Preserve the intended lesson order before replacing order_index
    # with temporary unique values.
    lessons_by_unit = {
        unit.id: sorted(
            unit.lessons,
            key=lambda item: (
                item.order_index if item.order_index > 0 else 9999,
                item.id,
            ),
        )
        for unit in units_sorted
    }

    # Move all existing rows to unique temporary values first.
    for unit in units_sorted:
        unit.order_index = -(100000 + unit.id)

        for lesson in lessons_by_unit[unit.id]:
            lesson.order_index = -(200000 + lesson.id)

    db.session.flush()

    # Apply the final sequential order using the preserved lists.
    for unit_index, unit in enumerate(units_sorted, start=1):
        unit.order_index = unit_index

        for lesson_index, lesson in enumerate(
            lessons_by_unit[unit.id],
            start=1,
        ):
            lesson.order_index = lesson_index

    db.session.flush()

    source.lesson_id = (
        resolved_sections[0]["lesson_id"]
        if len({item["lesson_id"] for item in resolved_sections}) == 1
        else None
    )
    source.is_active = True
    source.curriculum.processing_status = "ready"
    source.curriculum.processing_error = None
    db.session.flush()
    return len(chunk_data)
