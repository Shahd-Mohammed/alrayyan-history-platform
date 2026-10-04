import hashlib
import re
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
import pymupdf


def calculate_checksum(file_path):
    """
    Create a unique SHA-256 fingerprint for a file.

    It helps us detect exact duplicate files.
    """
    file_path = Path(file_path)
    sha256 = hashlib.sha256()

    with file_path.open("rb") as file:
        for block in iter(lambda: file.read(8192), b""):
            sha256.update(block)

    return sha256.hexdigest()


def extract_pdf(file_path):
    """
    Extract text from a PDF while preserving page numbers.
    """
    document = pymupdf.open(str(file_path))
    pages = []

    try:
        for page_number, page in enumerate(
            document,
            start=1,
        ):
            text = page.get_text("text") or ""

            pages.append(
                {
                    "page_number": page_number,
                    "text": text.strip(),
                }
            )

        return {
            "document_type": "pdf",
            "page_count": document.page_count,
            "pages": pages,
        }

    finally:
        document.close()

_ARABIC_ORDINALS = (
    "الأولى", "الثانية", "الثالثة", "الرابعة", "الخامسة",
    "السادسة", "السابعة", "الثامنة", "التاسعة", "العاشرة",
    "الحادية عشرة", "الثانية عشرة", "الثالثة عشرة", "الرابعة عشرة",
)


def _normalize_heading(text):
    """Normalize Word heading text before structural matching."""
    text = (text or "").replace("\u200f", "").replace("\u200e", "")
    text = text.replace("ـ", "")
    text = re.sub(r"[\\t\\r\\n]+", " ", text)
    return re.sub(r"\\s+", " ", text).strip()


def _arabic_number_pattern():
    ordinals = "|".join(map(re.escape, _ARABIC_ORDINALS))
    return rf"(?:{ordinals}|\\d+|[٠-٩]+)"


def _match_section_heading(text, kind):
    """
    Detect common Arabic Word headings for units and lessons.

    The matcher deliberately accepts several real-world Word formats instead
    of depending on one exact sentence:
    - الوحدة الأولى
    - الوحدة 1
    - الوحدة (1)
    - الوحدة رقم 1
    - الدرس الأول: حركات التحرر الوطني
    - الدرس 1 - حركات التحرر الوطني
    - الدرس الثاني حركات التحرر الوطني
    """
    normalized = _normalize_heading(text)
    if not normalized:
        return None

    label = r"(?:الوحدة|وحدة)" if kind == "unit" else r"(?:الدرس|درس)"
    number = _arabic_number_pattern()

    match = re.match(
        rf"^{label}\\s*(?:رقم\\s*)?\\(?{number}\\)?"
        rf"(?:\\s*[:：\\-–—.\\)]\\s*(.*)|\\s+(.+))?\\s*$",
        normalized,
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    trailing_title = (match.group(1) or match.group(2) or "").strip()

    if kind == "lesson":
        # Store the real lesson name when the heading contains one.
        # If there is no title after the lesson number, keep the full heading.
        return trailing_title or normalized

    # Units are usually identified by their number. Keep an optional
    # descriptive title when the Word file includes one.
    return normalized


def _docx_paragraph_texts(document):
    """
    Read all body paragraphs in Word XML order.

    This covers normal paragraphs, paragraphs inside tables, and text boxes /
    shapes that are stored in the document body. It does not rely on Word's
    visual page layout, so the parser works with different templates.
    """
    paragraphs = []

    for paragraph in document.element.body.iter(qn("w:p")):
        parts = []
        for node in paragraph.iter():
            if node.tag == qn("w:t"):
                parts.append(node.text or "")
            elif node.tag == qn("w:tab"):
                parts.append("\\t")

        text = _normalize_heading("".join(parts))
        if text:
            paragraphs.append(text)

    return paragraphs


def extract_docx(file_path):
    """
    Extract a Word curriculum and automatically build unit/lesson sections.

    The Word file does not need a table of contents. The parser scans the
    complete document and recognizes common Arabic unit/lesson headings.
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
    """
    Read a supported source and return its basic information.
    """
    file_path = Path(file_path)
    extension = file_path.suffix.lower()

    if extension == ".pdf":
        extracted = extract_pdf(file_path)
        text = "\n".join(
            page["text"]
            for page in extracted["pages"]
        )

    elif extension == ".docx":
        extracted = extract_docx(file_path)
        text = extracted["text"]

    else:
        raise ValueError(
            f"Unsupported file type: {extension}"
        )

    return {
        "filename": file_path.name,
        "path": str(file_path),
        "extension": extension,
        "checksum": calculate_checksum(file_path),
        "page_count": extracted["page_count"],
        "character_count": len(text),
        "text_preview": text[:300].replace("\n", " "),
    }