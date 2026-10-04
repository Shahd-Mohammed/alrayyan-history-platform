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


def _is_heading(paragraph):
    style_name = (getattr(paragraph.style, "name", "") or "").strip().lower()
    if any(token in style_name for token in ("heading", "title", "subtitle", "عنوان", "عنوان رئيسي")):
        return True

    runs = [run for run in paragraph.runs if run.text.strip()]
    return bool(runs) and all(run.bold for run in runs)


def _match_section_heading(text, kind):
    normalized = re.sub(r"\s+", " ", text.strip())
    if kind == "unit":
        pattern = (
            r"^(?:الوحدة|وحدة)\s+(?:"
            + "|".join(map(re.escape, _ARABIC_ORDINALS))
            + r"|\d+)(?:\s*[:\-–—.]\s*(.*))?$"
        )
    else:
        pattern = (
            r"^(?:الدرس|درس)\s+(?:"
            + "|".join(map(re.escape, _ARABIC_ORDINALS))
            + r"|\d+)(?:\s*[:\-–—.]\s*(.*))?$"
        )

    match = re.match(pattern, normalized, flags=re.IGNORECASE)
    if not match:
        return None

    title = (match.group(1) or "").strip()
    return normalized if not title else f"{normalized.split(':', 1)[0].strip()} — {title}"


def _docx_paragraph_texts(document):
    """Read Word paragraphs in XML order, including text inside text boxes."""
    paragraphs = []
    for paragraph in document.element.body.iter(qn("w:p")):
        parts = []
        for node in paragraph.iter():
            if node.tag == qn("w:t"):
                parts.append(node.text or "")
            elif node.tag == qn("w:tab"):
                parts.append("\t")
        text = re.sub(r"\s+", " ", "".join(parts)).strip()
        if text:
            paragraphs.append(text)
    return paragraphs


def _normalize_heading(text):
    return re.sub(r"\s+", " ", text.strip().replace("ـ", ""))


def _match_section_heading(text, kind):
    normalized = _normalize_heading(text)
    ordinals = "|".join(map(re.escape, _ARABIC_ORDINALS))
    label = r"(?:الوحدة|وحدة)" if kind == "unit" else r"(?:الدرس|درس)"
    match = re.match(
        rf"^{label}\s+(?:{ordinals}|\d+|[٠-٩]+)(?:\s*[:\-–—.]\s*(.*))?\s*$",
        normalized,
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    return normalized


def extract_docx(file_path):
    """
    Extract a Word document and detect units/lessons, including text boxes.
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