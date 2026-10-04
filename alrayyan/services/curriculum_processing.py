import json
from datetime import datetime, timezone
from pathlib import Path

from flask import current_app

from alrayyan.extensions import db
from alrayyan.models import ContentChunk
from alrayyan.services.document_reader import extract_docx, extract_pdf
from alrayyan.services.embeddings import generate_embeddings, get_embedding_settings
from alrayyan.services.text_processing import chunk_text, create_text_hash


def process_source_document(source):
    """Extract, chunk, and embed an already stored source document."""
    if not source.stored_path:
        raise ValueError("ملف المصدر غير موجود")

    upload_root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    file_path = (upload_root / source.stored_path).resolve()
    if not file_path.is_relative_to(upload_root) or not file_path.is_file():
        raise ValueError("ملف المصدر غير موجود على الخادم")

    extracted = (
        extract_pdf(file_path)
        if file_path.suffix.lower() == ".pdf"
        else extract_docx(file_path)
        if file_path.suffix.lower() == ".docx"
        else None
    )
    if extracted is None:
        raise ValueError("صيغة ملف المصدر غير مدعومة")

    pages = extracted.get("pages") or [{"page_number": None, "text": extracted.get("text", "")}]
    chunk_data = []
    index = 0
    for page in pages:
        for text in chunk_text(page.get("text", "")):
            chunk_data.append({
                "page_number": page.get("page_number"),
                "chunk_index": index,
                "text": text,
                "text_hash": create_text_hash(text),
                "token_count": len(text.split()),
            })
            index += 1

    if not chunk_data:
        raise ValueError("لم نستطع استخراج نص؛ قد يكون PDF عبارة عن صور ويحتاج OCR")

    embedding_settings = get_embedding_settings()
    vectors = []
    batch_size = current_app.config.get("EMBEDDING_BATCH_SIZE", 20)
    for start in range(0, len(chunk_data), batch_size):
        batch = chunk_data[start:start + batch_size]
        vectors.extend(generate_embeddings([item["text"] for item in batch]))

    embedded_at = datetime.now(timezone.utc).replace(tzinfo=None)

    ContentChunk.query.filter_by(source_id=source.id).delete(synchronize_session=False)
    for item, vector in zip(chunk_data, vectors):
        db.session.add(ContentChunk(
            source_id=source.id,
            lesson_id=source.lesson_id,
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
    source.is_active = True
    source.curriculum.processing_status = "ready"
    source.curriculum.processing_error = None
    db.session.flush()
    return len(chunk_data)
