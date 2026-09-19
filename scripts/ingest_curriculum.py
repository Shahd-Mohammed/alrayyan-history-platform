import sys
from pathlib import Path

from alrayyan import create_app
from alrayyan.extensions import db
from alrayyan.models import (
    ContentChunk,
    Curriculum,
    Lesson,
    SourceDocument,
    Unit,
)
from alrayyan.services.document_reader import (
    calculate_checksum,
    extract_docx,
    extract_pdf,
)
from alrayyan.services.text_processing import (
    chunk_text,
    clean_arabic_text,
    create_text_hash,
)


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


PROJECT_ROOT = Path(__file__).resolve().parents[1]

SEMESTER_ONE_FOLDER = (
    PROJECT_ROOT
    / "curriculum"
    / "raw"
    / "grade_11"
    / "semester_1"
)

SEMESTER_TWO_FOLDER = (
    PROJECT_ROOT
    / "curriculum"
    / "raw"
    / "grade_11"
    / "semester_2"
)


LESSON_DEFINITIONS = [
    {
        "unit_order": 1,
        "unit_title": "الوحدة الأولى",
        "lesson_order": 1,
        "title": "الاستعمار: مفهومه ودوافعه وأشكاله",
        "slug": "colonialism-concept-motives-forms",
        "marker": "الدرس الأول: الاستعمار مفهومه ودوافعه وأشكاله",
    },
    {
        "unit_order": 1,
        "unit_title": "الوحدة الأولى",
        "lesson_order": 2,
        "title": "الاحتلال الفرنسي والإسباني للمغرب",
        "slug": "occupation-of-morocco",
        "marker": "الاحتلال الفرنسي والاسباني للمغرب",
    },
    {
        "unit_order": 1,
        "unit_title": "الوحدة الأولى",
        "lesson_order": 3,
        "title": "الحماية الفرنسية على تونس والحماية البريطانية على مصر",
        "slug": "tunisia-egypt-protectorates",
        "marker": "الحماية الفرنسية على تونس والحماية البريطانية على مصر",
    },
    {
        "unit_order": 1,
        "unit_title": "الوحدة الأولى",
        "lesson_order": 4,
        "title": "الانتداب الفرنسي على سوريا ولبنان",
        "slug": "french-mandate-syria-lebanon",
        "marker": "الانتداب الفرنسي على سوريا ولبنان",
    },
    {
        "unit_order": 1,
        "unit_title": "الوحدة الأولى",
        "lesson_order": 5,
        "title": "الانتداب البريطاني على العراق والأردن وفلسطين",
        "slug": "british-mandate-iraq-jordan-palestine",
        "marker": "الانتداب البريطاني على العراق والأردن وفلسطين",
    },
    {
        "unit_order": 2,
        "unit_title": "الوحدة الثانية",
        "lesson_order": 1,
        "title": "الاستعمار الاستيطاني",
        "slug": "settler-colonialism",
        "marker": "الدرس الأول: الاستعمار الاستيطاني",
    },
    {
        "unit_order": 2,
        "unit_title": "الوحدة الثانية",
        "lesson_order": 2,
        "title": "الاستعمار الاستيطاني في الجزائر",
        "slug": "settler-colonialism-algeria",
        "marker": "الدرس الثاني: الاستعمار الاستيطاني في الجزائر",
    },
    {
        "unit_order": 2,
        "unit_title": "الوحدة الثانية",
        "lesson_order": 3,
        "title": "الاستعمار الاستيطاني الصهيوني في فلسطين",
        "slug": "zionist-settler-colonialism-palestine",
        "marker": "الاستعمار الاستيطاني الصهيوني في فلسطين",
    },
]


def find_one_file(folder, extension):
    """
    Return one matching file from a source folder.
    """
    files = sorted(
        folder.glob(f"*{extension}")
    )

    if not files:
        return None

    return files[0]


def get_or_create_curriculum(
    semester,
    is_active,
):
    curriculum = Curriculum.query.filter_by(
        grade="11",
        semester=semester,
        academic_year="2025-2026",
        version="1.0",
    ).first()

    if curriculum is None:
        curriculum = Curriculum(
            name=(
                "الدراسات التاريخية "
                f"للصف الحادي عشر - {semester}"
            ),
            subject="الدراسات التاريخية",
            grade="11",
            semester=semester,
            academic_year="2025-2026",
            version="1.0",
            is_active=is_active,
        )

        db.session.add(curriculum)
        db.session.flush()

    else:
        curriculum.is_active = is_active

    return curriculum


def get_or_create_units_and_lessons(curriculum):
    """
    Create the semester-one units and lessons.
    """
    lessons_by_slug = {}

    for definition in LESSON_DEFINITIONS:
        unit = Unit.query.filter_by(
            curriculum_id=curriculum.id,
            order_index=definition["unit_order"],
        ).first()

        if unit is None:
            unit = Unit(
                curriculum_id=curriculum.id,
                title=definition["unit_title"],
                order_index=definition["unit_order"],
            )

            db.session.add(unit)
            db.session.flush()

        lesson = Lesson.query.filter_by(
            slug=definition["slug"],
        ).first()

        if lesson is None:
            lesson = Lesson(
                unit_id=unit.id,
                title=definition["title"],
                slug=definition["slug"],
                order_index=definition["lesson_order"],
                is_published=True,
            )

            db.session.add(lesson)
            db.session.flush()

        else:
            lesson.unit_id = unit.id
            lesson.title = definition["title"]
            lesson.order_index = definition["lesson_order"]

        lessons_by_slug[definition["slug"]] = lesson

    return lessons_by_slug


def upsert_source(
    curriculum,
    file_path,
    title,
    source_type,
    priority,
    is_primary,
    is_active,
    page_count=None,
):
    """
    Create or update source metadata using its checksum.
    """
    checksum = calculate_checksum(file_path)

    source = SourceDocument.query.filter_by(
        curriculum_id=curriculum.id,
        checksum=checksum,
    ).first()

    relative_path = file_path.relative_to(
        PROJECT_ROOT
    ).as_posix()

    if source is None:
        source = SourceDocument(
            curriculum_id=curriculum.id,
            title=title,
            source_type=source_type,
            original_filename=file_path.name,
            stored_path=relative_path,
            page_count=page_count,
            checksum=checksum,
            academic_year=curriculum.academic_year,
            priority=priority,
            is_primary=is_primary,
            is_active=is_active,
        )

        db.session.add(source)
        db.session.flush()

    else:
        source.title = title
        source.source_type = source_type
        source.original_filename = file_path.name
        source.stored_path = relative_path
        source.page_count = page_count
        source.priority = priority
        source.is_primary = is_primary
        source.is_active = is_active

    return source


def replace_source_chunks(source):
    """
    Delete only derived chunks for one source.

    The original PDF or Word file is never deleted.
    """
    ContentChunk.query.filter_by(
        source_id=source.id
    ).delete(
        synchronize_session=False
    )

    db.session.flush()


def ingest_official_book(
    curriculum,
    pdf_path,
):
    """
    Store official-book chunks with page numbers.
    """
    extracted = extract_pdf(pdf_path)

    source = upsert_source(
        curriculum=curriculum,
        file_path=pdf_path,
        title="الكتاب الرسمي للدراسات التاريخية",
        source_type="official_textbook",
        priority=2,
        is_primary=False,
        is_active=True,
        page_count=extracted["page_count"],
    )

    replace_source_chunks(source)

    chunk_index = 0

    for page in extracted["pages"]:
        page_text = clean_arabic_text(
            page["text"]
        )

        for text_chunk in chunk_text(page_text):
            chunk_index += 1

            chunk = ContentChunk(
                source_id=source.id,
                lesson_id=None,
                page_number=page["page_number"],
                chunk_index=chunk_index,
                text=text_chunk,
                text_hash=create_text_hash(
                    text_chunk
                ),
                token_count=len(
                    text_chunk.split()
                ),
            )

            db.session.add(chunk)

    print(
        f"Official textbook: "
        f"{chunk_index} chunk(s)"
    )


def split_notes_by_lessons(notes_text):
    """
    Split teacher notes using known lesson headings.
    """
    cleaned_notes = clean_arabic_text(
        notes_text
    )

    located_sections = []
    search_start = 0

    for definition in LESSON_DEFINITIONS:
        marker = definition["marker"]

        marker_position = cleaned_notes.find(
            marker,
            search_start,
        )

        if marker_position == -1:
            print(
                "Warning: lesson marker was not found: "
                f"{marker}"
            )
            continue

        located_sections.append(
            {
                "definition": definition,
                "start": marker_position,
            }
        )

        search_start = marker_position + len(marker)

    sections = []

    for index, located in enumerate(
        located_sections
    ):
        start = located["start"]

        if index + 1 < len(located_sections):
            end = located_sections[index + 1]["start"]
        else:
            end = len(cleaned_notes)

        section_text = cleaned_notes[start:end].strip()

        sections.append(
            {
                "definition": located["definition"],
                "text": section_text,
            }
        )

    return sections


def ingest_teacher_notes(
    curriculum,
    notes_path,
    lessons_by_slug,
):
    """
    Store teacher-note chunks and connect them to lessons.
    """
    extracted = extract_docx(notes_path)

    source = upsert_source(
        curriculum=curriculum,
        file_path=notes_path,
        title="ملزمة الريان في الدراسات التاريخية",
        source_type="teacher_notes",
        priority=1,
        is_primary=True,
        is_active=True,
        page_count=None,
    )

    replace_source_chunks(source)

    sections = split_notes_by_lessons(
        extracted["text"]
    )

    chunk_index = 0

    for section in sections:
        definition = section["definition"]
        lesson = lessons_by_slug[
            definition["slug"]
        ]

        for text_chunk in chunk_text(
            section["text"]
        ):
            chunk_index += 1

            chunk = ContentChunk(
                source_id=source.id,
                lesson_id=lesson.id,
                page_number=None,
                chunk_index=chunk_index,
                text=text_chunk,
                text_hash=create_text_hash(
                    text_chunk
                ),
                token_count=len(
                    text_chunk.split()
                ),
            )

            db.session.add(chunk)

    print(
        f"Teacher notes: "
        f"{chunk_index} chunk(s)"
    )


def register_inactive_semester_two(
    curriculum,
):
    """
    Register semester two without making it searchable.
    """
    official_folder = (
        SEMESTER_TWO_FOLDER
        / "official"
    )

    pdf_path = find_one_file(
        official_folder,
        ".pdf",
    )

    if pdf_path is None:
        print(
            "Semester-two book was not found. "
            "Skipping its registration."
        )
        return

    extracted = extract_pdf(pdf_path)

    upsert_source(
        curriculum=curriculum,
        file_path=pdf_path,
        title=(
            "الكتاب الرسمي للدراسات التاريخية "
            "- الفصل الثاني"
        ),
        source_type="official_textbook",
        priority=100,
        is_primary=False,
        is_active=False,
        page_count=extracted["page_count"],
    )

    print(
        "Semester-two book registered as inactive."
    )


def run_ingestion():
    app = create_app()

    with app.app_context():
        try:
            semester_one = get_or_create_curriculum(
                semester="الفصل الأول",
                is_active=True,
            )

            semester_two = get_or_create_curriculum(
                semester="الفصل الثاني",
                is_active=False,
            )

            lessons_by_slug = (
                get_or_create_units_and_lessons(
                    semester_one
                )
            )

            official_pdf = find_one_file(
                SEMESTER_ONE_FOLDER / "official",
                ".pdf",
            )

            teacher_notes = find_one_file(
                SEMESTER_ONE_FOLDER
                / "teacher_notes",
                ".docx",
            )

            if official_pdf is None:
                raise FileNotFoundError(
                    "Semester-one official PDF "
                    "was not found."
                )

            if teacher_notes is None:
                raise FileNotFoundError(
                    "Semester-one teacher notes "
                    "were not found."
                )

            ingest_official_book(
                semester_one,
                official_pdf,
            )

            ingest_teacher_notes(
                semester_one,
                teacher_notes,
                lessons_by_slug,
            )

            register_inactive_semester_two(
                semester_two
            )

            db.session.commit()

            print("=" * 60)
            print("Knowledge preparation completed.")
            print(
                f"Curricula: "
                f"{Curriculum.query.count()}"
            )
            print(
                f"Units: "
                f"{Unit.query.count()}"
            )
            print(
                f"Lessons: "
                f"{Lesson.query.count()}"
            )
            print(
                f"Sources: "
                f"{SourceDocument.query.count()}"
            )
            print(
                f"Chunks: "
                f"{ContentChunk.query.count()}"
            )

        except Exception:
            db.session.rollback()
            raise


if __name__ == "__main__":
    run_ingestion()