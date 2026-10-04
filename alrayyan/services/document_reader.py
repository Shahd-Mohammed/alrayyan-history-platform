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
    "الاولى", "الثانية", "الثالثة", "الرابعة", "الخامسة",
    "السادسة", "السابعة", "الثامنة", "التاسعة", "العاشرة",
    "الحادية عشرة", "الثانية عشرة", "الثالثة عشرة", "الرابعة عشرة",
)

_ARABIC_MASCULINE_ORDINALS = (
    "الاول", "الثاني", "الثالث", "الرابع", "الخامس",
    "السادس", "السابع", "الثامن", "التاسع", "العاشر",
    "الحادي عشر", "الثاني عشر", "الثالث عشر", "الرابع عشر",
)


def _normalize_heading(text):
    """Normalize Arabic variations before structural matching."""
    text = (text or "").replace("\u200f", "").replace("\u200e", "")
    text = text.replace("ـ", "")
    text = re.sub(r"[\u064B-\u065F\u0670\u06D6-\u06ED]", "", text)
    text = text.translate(str.maketrans({
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ٱ": "ا",
        "ى": "ي",
        "٠": "0",
        "١": "1",
        "٢": "2",
        "٣": "3",
        "٤": "4",
        "٥": "5",
        "٦": "6",
        "٧": "7",
        "٨": "8",
        "٩": "9",
    }))
    text = re.sub(r"[\t\r\n]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _arabic_number_pattern():
    ordinals = "|".join(
        map(re.escape, _ARABIC_ORDINALS + _ARABIC_MASCULINE_ORDINALS)
    )
    return rf"(?:{ordinals}|\d+)"


def _match_section_heading(text, kind):
    """Detect common Arabic unit and lesson heading formats."""
    normalized = _normalize_heading(text)
    if not normalized:
        return None

    label = r"(?:الوحدة|وحدة)" if kind == "unit" else r"(?:الدرس|درس)"
    number = _arabic_number_pattern()

    numbered_match = re.match(
        rf"^{label}\s*(?:رقم\s*)?\(?{number}\)?"
        rf"(?:\s*[:：\-–—.\)]\s*(.*)|\s+(.+))?\s*$",
        normalized,
        flags=re.IGNORECASE,
    )
    if numbered_match:
        trailing_title = (
            numbered_match.group(1) or numbered_match.group(2) or ""
        ).strip()
        if kind == "lesson":
            return trailing_title or normalized
        return normalized

    unnumbered_match = re.match(
        rf"^{label}\s*[:：\-–—.]\s*(.+?)\s*$",
        normalized,
        flags=re.IGNORECASE,
    )
    if unnumbered_match:
        return unnumbered_match.group(1).strip()

    return None


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


def _docx_paragraph_records(document):
    """Read Word paragraphs in document order, including text boxes and styles."""
    style_names = {
        style.style_id: style.name
        for style in document.styles
        if getattr(style, "style_id", None)
    }
    records = []

    for paragraph in document.element.body.iter(qn("w:p")):
        parts = []
        style_id = None

        p_pr = paragraph.find(qn("w:pPr"))
        if p_pr is not None:
            p_style = p_pr.find(qn("w:pStyle"))
            if p_style is not None:
                style_id = p_style.get(qn("w:val"))

        for node in paragraph.iter():
            if node.tag == qn("w:t"):
                parts.append(node.text or "")
            elif node.tag == qn("w:tab"):
                parts.append("\t")

        text = _normalize_heading("".join(parts))
        if text:
            records.append({
                "text": text,
                "style_name": style_names.get(style_id, style_id or ""),
            })

    return records


def _heading_level_from_style(style_name):
    """Return Word heading level when a standard/custom heading style is used."""
    normalized = _normalize_heading(style_name).lower()
    match = re.search(r"(?:heading|عنوان|العنوان)\s*([1-9])", normalized)
    if match:
        return int(match.group(1))

    compact = re.sub(r"\s+", "", normalized)
    match = re.search(r"(?:heading|عنوان|العنوان)([1-9])", compact)
    return int(match.group(1)) if match else None


def _docx_paragraph_texts(document):
    """Keep the original simple text-only helper for compatibility."""
    return [record["text"] for record in _docx_paragraph_records(document)]

def extract_docx(file_path):
    """
    Extract a Word curriculum and automatically build unit/lesson sections.
    Supports explicit Arabic headings and Word Heading styles.
    """
    document = Document(str(file_path))
    records = _docx_paragraph_records(document)

    sections = []
    current_unit = None
    current_lesson = None
    current_lines = []
    found_structured_heading = False

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

    for record in records:
        text = record["text"]
        style_level = _heading_level_from_style(record["style_name"])

        unit_heading = _match_section_heading(text, "unit")
        lesson_heading = _match_section_heading(text, "lesson")

        if not unit_heading and style_level == 1:
            unit_heading = text
        if not lesson_heading and style_level is not None and style_level >= 2:
            lesson_heading = text

        if unit_heading:
            flush_section()
            current_unit = unit_heading
            current_lesson = None
            found_structured_heading = True
            continue

        if lesson_heading:
            flush_section()
            current_lesson = lesson_heading
            found_structured_heading = True
            continue

        current_lines.append(text)

    flush_section()

    if found_structured_heading and sections:
        first_structured_index = next(
            (
                index for index, section in enumerate(sections)
                if section["unit_title"] is not None
                or section["lesson_title"] is not None
            ),
            None,
        )
        if first_structured_index is not None:
            sections = sections[first_structured_index:]

    if not sections and records:
        sections = [{
            "unit_title": None,
            "lesson_title": None,
            "text": "\n".join(record["text"] for record in records),
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
