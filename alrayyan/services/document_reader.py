import hashlib
import re
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
import pymupdf


def calculate_checksum(file_path):
    """Create a unique SHA-256 fingerprint for a file."""
    file_path = Path(file_path)
    sha256 = hashlib.sha256()

    with file_path.open("rb") as file:
        for block in iter(lambda: file.read(8192), b""):
            sha256.update(block)

    return sha256.hexdigest()


_ARABIC_ORDINALS = (
    "الأولى", "الثانية", "الثالثة", "الرابعة", "الخامسة",
    "السادسة", "السابعة", "الثامنة", "التاسعة", "العاشرة",
    "الحادية عشرة", "الثانية عشرة", "الثالثة عشرة", "الرابعة عشرة",
)

_ARABIC_MASCULINE_ORDINALS = (
    "الأول", "الثاني", "الثالث", "الرابع", "الخامس",
    "السادس", "السابع", "الثامن", "التاسع", "العاشر",
    "الحادي عشر", "الثاني عشر", "الثالث عشر", "الرابع عشر",
)


def _normalize_heading(text):
    """Normalize text before structural matching."""
    text = (text or "").replace("\u200f", "").replace("\u200e", "")
    text = text.replace("ـ", "")
    text = re.sub(r"[\t\r\n]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _arabic_number_pattern():
    ordinals = "|".join(
        map(re.escape, _ARABIC_ORDINALS + _ARABIC_MASCULINE_ORDINALS)
    )
    return rf"(?:{ordinals}|\d+|[٠-٩]+)"


def _match_section_heading(text, kind):
    """Detect common Arabic unit and lesson heading formats."""
    normalized = _normalize_heading(text)
    if not normalized:
        return None

    label = r"(?:الوحدة|وحدة)" if kind == "unit" else r"(?:الدرس|درس)"
    number = _arabic_number_pattern()

    match = re.match(
        rf"^{label}\s*(?:رقم\s*)?\(?{number}\)?"
        rf"(?:\s*[:：\-–—.\)]\s*(.*)|\s+(.+))?\s*$",
        normalized,
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    trailing_title = (match.group(1) or match.group(2) or "").strip()
    if kind == "lesson":
        return trailing_title or normalized
    return normalized


def _text_is_usable(text):
    """Reject empty or badly encoded Arabic PDF text."""
    text = (text or "").strip()
    if len(text) < 20:
        return False

    control_count = sum(1 for char in text if ord(char) < 32 and char not in "\n\t")
    arabic_count = len(re.findall(r"[\u0600-\u06FF]", text))
    replacement_count = text.count("\ufffd")

    if replacement_count > 0 or control_count > 3:
        return False

    if arabic_count >= 5:
        return True

    word_count = len(re.findall(r"[A-Za-z]{2,}", text))
    return word_count >= 5


def _ocr_pdf_page(page):
    """Run Arabic OCR through PyMuPDF/Tesseract when normal extraction fails."""
    text_page = page.get_textpage_ocr(
        language="ara+eng",
        dpi=200,
        full=True,
    )
    return page.get_text("text", textpage=text_page).strip()


def _build_sections_from_pages(pages):
    """Turn page text into unit/lesson sections without requiring a TOC."""
    sections = []
    current_unit = None
    current_lesson = None
    current_lines = []
    current_start_page = None

    def flush_section():
        nonlocal current_lines, current_start_page
        text = "\n".join(current_lines).strip()
        if text:
            sections.append({
                "unit_title": current_unit,
                "lesson_title": current_lesson,
                "page_number": current_start_page,
                "text": text,
            })
        current_lines = []
        current_start_page = None

    for page in pages:
        page_number = page["page_number"]
        for raw_line in (page.get("text") or "").splitlines():
            text = _normalize_heading(raw_line)
            if not text:
                continue

            unit_heading = _match_section_heading(text, "unit")
            lesson_heading = _match_section_heading(text, "lesson")

            if unit_heading:
                flush_section()
                current_unit = unit_heading
                current_lesson = None
                current_start_page = page_number
                continue

            if lesson_heading:
                flush_section()
                current_lesson = lesson_heading
                current_start_page = page_number
                continue

            if current_start_page is None:
                current_start_page = page_number
            current_lines.append(raw_line.strip())

    flush_section()

    if not sections:
        combined = "\n".join(
            page["text"].strip()
            for page in pages
            if page.get("text")
        ).strip()
        if combined:
            sections = [{
                "unit_title": None,
                "lesson_title": None,
                "page_number": pages[0]["page_number"] if pages else None,
                "text": combined,
            }]

    return sections


def extract_pdf(file_path):
    """
    Extract a PDF using normal text extraction first and Arabic OCR as a
    fallback. Then automatically detect units and lessons.
    """
    document = pymupdf.open(str(file_path))
    pages = []

    try:
        for page_number, page in enumerate(document, start=1):
            text = (page.get_text("text") or "").strip()

            if not _text_is_usable(text):
                try:
                    text = _ocr_pdf_page(page)
                except Exception:
                    pass

            pages.append({
                "page_number": page_number,
                "text": text,
            })

        sections = _build_sections_from_pages(pages)

        return {
            "document_type": "pdf",
            "page_count": document.page_count,
            "pages": pages,
            "text": "\n".join(section["text"] for section in sections),
            "sections": sections,
        }

    finally:
        document.close()


def _docx_paragraph_texts(document):
    """Read Word paragraphs in document order, including XML text boxes."""
    paragraphs = []

    for paragraph in document.element.body.iter(qn("w:p")):
        parts = []
        for node in paragraph.iter():
            if node.tag == qn("w:t"):
                parts.append(node.text or "")
            elif node.tag == qn("w:tab"):
                parts.append("\t")

        text = _normalize_heading("".join(parts))
        if text:
            paragraphs.append(text)

    return paragraphs


def extract_docx(file_path):
    """
    Extract a Word curriculum and automatically build unit/lesson sections.
    No table of contents is required.
    """
    document = Document(str(file_path))
    paragraphs = _docx_paragraph_texts(document)

    sections = []
    current_unit = None
    current_lesson = None
    current_lines = []

    def flush_section():
        nonlocal current_lines
        text = "\n".join(current_lines).strip()
        if text:
            sections.append({
                "unit_title": current_unit,
                "lesson_title": current_lesson,
                "text": text,
            })
        current_lines = []

    for text in paragraphs:
        unit_heading = _match_section_heading(text, "unit")
        lesson_heading = _match_section_heading(text, "lesson")

        if unit_heading:
            flush_section()
            current_unit = unit_heading
            current_lesson = None
            continue

        if lesson_heading:
            flush_section()
            current_lesson = lesson_heading
            continue

        current_lines.append(text)

    flush_section()

    if not sections and paragraphs:
        sections = [{
            "unit_title": None,
            "lesson_title": None,
            "text": "\n".join(paragraphs),
        }]

    return {
        "document_type": "docx",
        "page_count": None,
        "text": "\n".join(section["text"] for section in sections),
        "sections": sections,
    }


def inspect_document(file_path):
    """Read a supported source and return its basic information."""
    file_path = Path(file_path)
    extension = file_path.suffix.lower()

    if extension == ".pdf":
        extracted = extract_pdf(file_path)
        text = extracted["text"]
    elif extension == ".docx":
        extracted = extract_docx(file_path)
        text = extracted["text"]
    else:
        raise ValueError(f"Unsupported file type: {extension}")

    return {
        "filename": file_path.name,
        "path": str(file_path),
        "extension": extension,
        "checksum": calculate_checksum(file_path),
        "page_count": extracted["page_count"],
        "character_count": len(text),
        "text_preview": text[:300].replace("\n", " "),
    }
