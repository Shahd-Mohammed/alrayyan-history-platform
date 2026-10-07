import hashlib
import os
import re
import shutil
import subprocess
import tempfile
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
    """Build a pattern for Arabic ordinal numbers and numeric forms."""
    ordinals = "|".join(
        re.escape(_normalize_heading(value))
        for value in (_ARABIC_ORDINALS + _ARABIC_MASCULINE_ORDINALS)
    )
    return f"(?:{ordinals}|\\d+)"


def _match_section_heading(text, kind):
    """Detect common Arabic unit and lesson heading formats."""
    normalized = _normalize_heading(text)
    if not normalized:
        return None

    # Some Word curriculum files place a grade/page number
    # immediately before the heading, such as "11الوحدة الأولى".
    normalized = re.sub(r"^\d+\s*", "", normalized)

    if kind == "unit":
        label = r"(?:الوحدة|وحدة)"
    else:
        label = r"(?:الدرس|درس)"

    number = _arabic_number_pattern()

    # Numbered headings:
    # الوحدة الأولى
    # الوحدة 1
    # الدرس الأول
    # الدرس 1
    # الدرس رقم 1
    pattern = (
        r"^"
        + label
        + r"\s*(?:رقم\s*)?\(?"
        + number
        + r"\)?"
        + r"(?:\s*[:：\-–—.)]\s*(.*)|\s+(.+))?"
        + r"\s*$"
    )

    numbered_match = re.match(
        pattern,
        normalized,
        flags=re.IGNORECASE,
    )

    if numbered_match:
        trailing_title = (
            numbered_match.group(1)
            or numbered_match.group(2)
            or ""
        ).strip()

        if kind == "lesson":
            return trailing_title or normalized

        return normalized.split(":", 1)[0].strip()

    # Unnumbered headings:
    # الوحدة: عنوان الوحدة
    # الدرس: عنوان الدرس
    # الوحدة عنوان الوحدة
    # الدرس عنوان الدرس
    unnumbered_pattern = (
        r"^"
        + label
        + r"(?:\s*[:：\-–—.]\s*|\s+)(.+?)"
        + r"\s*$"
    )

    unnumbered_match = re.match(
        unnumbered_pattern,
        normalized,
        flags=re.IGNORECASE,
    )

    if unnumbered_match:
        return unnumbered_match.group(1).strip()

    return None


def _is_standalone_section_marker(text, kind):
    """Return True when an OCR line is only a unit/lesson marker."""
    normalized = _normalize_heading(text)
    normalized = re.sub(r"^\d+\s*", "", normalized)

    if kind == "unit":
        label = r"(?:الوحدة|وحدة)"
    else:
        label = r"(?:الدرس|درس)"

    number = _arabic_number_pattern()
    return bool(
        re.fullmatch(
            rf"{label}\s*(?:رقم\s*)?\(?{number}\)?",
            normalized,
            flags=re.IGNORECASE,
        )
        or re.fullmatch(label, normalized, flags=re.IGNORECASE)
    )


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


def _tesseract_command():
    """Resolve Tesseract across local Windows and Linux/Render."""
    configured = os.getenv("TESSERACT_CMD")
    if configured:
        return configured

    discovered = shutil.which("tesseract")
    if discovered:
        return discovered

    windows_path = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    if windows_path.exists():
        return str(windows_path)

    return None


def _ocr_pdf_page(page):
    """Run direct Tesseract OCR on a rendered PDF page."""
    tesseract = _tesseract_command()
    if not tesseract:
        raise RuntimeError("Tesseract executable was not found.")

    dpi = int(os.getenv("CURRICULUM_OCR_DPI", "300"))
    psm = os.getenv("CURRICULUM_OCR_PSM", "6")

    with tempfile.TemporaryDirectory(prefix="curriculum_ocr_") as temp_dir:
        image_path = Path(temp_dir) / "page.png"
        pixmap = page.get_pixmap(dpi=dpi, alpha=False)
        pixmap.save(str(image_path))

        result = subprocess.run(
            [
                tesseract,
                str(image_path),
                "stdout",
                "-l",
                "ara+eng",
                "--psm",
                psm,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Tesseract OCR failed with exit code {result.returncode}: "
                f"{result.stderr.strip()}"
            )

        text = result.stdout.strip()

        if len(text) < 50 and psm != "3":
            fallback = subprocess.run(
                [
                    tesseract,
                    str(image_path),
                    "stdout",
                    "-l",
                    "ara+eng",
                    "--psm",
                    "3",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if fallback.returncode == 0 and len(fallback.stdout.strip()) > len(text):
                text = fallback.stdout.strip()

        return text


def _build_sections_from_pages(pages):
    """Turn page text into unit/lesson sections without requiring a TOC."""
    sections = []
    current_unit = None
    current_lesson = None
    current_lines = []
    current_start_page = None
    pending_heading = None

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
        raw_lines = [
            raw_line.strip()
            for raw_line in (page.get("text") or "").splitlines()
            if _normalize_heading(raw_line)
        ]

        # Table-of-contents pages often contain many lesson markers in a
        # compact list. They are navigation metadata, not lesson content.
        structural_hits = 0
        for raw_line in raw_lines:
            normalized_line = _normalize_heading(raw_line)
            if (
                _is_standalone_section_marker(normalized_line, "unit")
                or _is_standalone_section_marker(normalized_line, "lesson")
                or _match_section_heading(normalized_line, "unit")
                or _match_section_heading(normalized_line, "lesson")
            ):
                structural_hits += 1

        if structural_hits >= 3:
            continue

        for raw_line in raw_lines:
            text = _normalize_heading(raw_line)
            if not text:
                continue

            unit_heading = _match_section_heading(text, "unit")
            lesson_heading = _match_section_heading(text, "lesson")

            if _is_standalone_section_marker(text, "unit"):
                flush_section()
                current_unit = None
                current_lesson = None
                current_start_page = page_number
                pending_heading = "unit"
                continue

            if _is_standalone_section_marker(text, "lesson"):
                flush_section()
                current_lesson = None
                current_start_page = page_number
                pending_heading = "lesson"
                continue

            if unit_heading:
                flush_section()
                current_unit = unit_heading
                current_lesson = None
                current_start_page = page_number
                pending_heading = None
                continue

            if lesson_heading:
                flush_section()
                current_lesson = lesson_heading
                current_start_page = page_number
                pending_heading = None
                continue

            if pending_heading:
                if re.fullmatch(r"\d+", text):
                    continue

                if pending_heading == "unit":
                    current_unit = text
                    current_lesson = None
                else:
                    current_lesson = text

                pending_heading = None
                if current_start_page is None:
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
                text = _ocr_pdf_page(page)

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

    The parser supports:
    - Unit headings with Arabic or numeric ordinals.
    - Lesson headings with or without a title on the same line.
    - Unit headings that also mention a lesson number.
    - Lesson titles placed in the paragraph immediately after the lesson marker.
    - Standard Word heading styles when available.
    """
    document = Document(str(file_path))
    records = _docx_paragraph_records(document)

    sections = []
    current_unit = None
    current_lesson = None
    current_lines = []
    pending_lesson = False
    found_structured_heading = False

    def flush_section():
        nonlocal current_lines
        text_value = "\n".join(current_lines).strip()

        if text_value:
            sections.append({
                "unit_title": current_unit,
                "lesson_title": current_lesson,
                "text": text_value,
            })

        current_lines = []

    for record in records:
        text_value = record["text"].strip()
        style_level = _heading_level_from_style(record["style_name"])

        unit_heading = _match_section_heading(text_value, "unit")
        lesson_heading = _match_section_heading(text_value, "lesson")

        if not unit_heading and style_level == 1:
            unit_heading = text_value

        if not lesson_heading and style_level is not None and style_level >= 2:
            lesson_heading = text_value

        # Detect a unit heading first.
        if unit_heading:
            flush_section()

            current_unit = unit_heading
            current_lesson = None
            current_lines = []
            pending_lesson = False
            found_structured_heading = True

            # Example:
            # "الوحدة الأولى: الدرس الثاني"
            # The unit matcher returns "الوحدة الأولى".
            # If the original line also contains "الدرس", remember that
            # the next meaningful paragraph is the lesson title.
            normalized = _normalize_heading(text_value)
            normalized_without_prefix = re.sub(r"^\d+\s*", "", normalized)

            if "الدرس" in normalized_without_prefix or "درس" in normalized_without_prefix:
                pending_lesson = True

            continue

        # Detect a lesson heading.
        if lesson_heading:
            flush_section()

            current_lesson = lesson_heading
            current_lines = []
            pending_lesson = False
            found_structured_heading = True

            # If the heading contains only "الدرس الرابع" or similar,
            # the next paragraph is expected to contain the actual title.
            normalized_lesson = _normalize_heading(text_value)
            normalized_lesson_without_prefix = re.sub(
                r"^\d+\s*",
                "",
                normalized_lesson,
            )

            if lesson_heading == normalized_lesson_without_prefix:
                pending_lesson = True

            continue

        # Ignore standalone grade/page markers such as "11".
        # They appear between structural headings and real content.
        if re.fullmatch(r"\d+", _normalize_heading(text_value)):
            if not current_lines:
                continue

        # If a lesson marker was found without its title, use the next
        # meaningful paragraph as the actual lesson title.
        if pending_lesson:
            # Word files may place the grade/page number on a separate
            # paragraph between the lesson heading and its real title.
            if re.fullmatch(r"\d+", _normalize_heading(text_value)):
                continue

            current_lesson = text_value
            pending_lesson = False
            continue

        current_lines.append(text_value)

    flush_section()

    if found_structured_heading and sections:
        first_structured_index = next(
            (
                index
                for index, section in enumerate(sections)
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
