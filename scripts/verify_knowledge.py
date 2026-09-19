import sys
from pathlib import Path

from alrayyan import create_app
from alrayyan.models import (
    ContentChunk,
    Curriculum,
    Lesson,
    SourceDocument,
    Unit,
)


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


PROJECT_ROOT = Path(__file__).resolve().parents[1]
failures = []


def check(condition, message):
    if condition:
        print(f"PASS: {message}")
    else:
        print(f"FAIL: {message}")
        failures.append(message)


def verify():
    app = create_app()

    with app.app_context():
        curricula = Curriculum.query.all()
        units = Unit.query.all()
        lessons = Lesson.query.all()
        sources = SourceDocument.query.all()
        chunks = ContentChunk.query.all()

        check(
            len(curricula) == 2,
            "Two curricula exist",
        )

        check(
            len(units) == 2,
            "Two semester-one units exist",
        )

        check(
            len(lessons) == 8,
            "Eight semester-one lessons exist",
        )

        check(
            len(sources) == 3,
            "Three source documents exist",
        )

        check(
            len(chunks) > 0,
            "Knowledge chunks exist",
        )

        semester_one = Curriculum.query.filter_by(
            semester="الفصل الأول"
        ).first()

        semester_two = Curriculum.query.filter_by(
            semester="الفصل الثاني"
        ).first()

        check(
            semester_one is not None
            and semester_one.is_active,
            "Semester one is active",
        )

        check(
            semester_two is not None
            and not semester_two.is_active,
            "Semester two is inactive",
        )

        active_sources = (
            SourceDocument.query
            .filter_by(is_active=True)
            .all()
        )

        inactive_sources = (
            SourceDocument.query
            .filter_by(is_active=False)
            .all()
        )

        check(
            len(active_sources) == 2,
            "Exactly two sources are active",
        )

        check(
            len(inactive_sources) == 1,
            "Exactly one source is inactive",
        )

        teacher_notes = (
            SourceDocument.query
            .filter_by(
                source_type="teacher_notes",
                is_active=True,
            )
            .first()
        )

        official_book = (
            SourceDocument.query
            .filter_by(
                source_type="official_textbook",
                is_active=True,
            )
            .first()
        )

        semester_two_book = (
            SourceDocument.query
            .filter_by(
                source_type="official_textbook",
                is_active=False,
            )
            .first()
        )

        check(
            teacher_notes is not None,
            "Teacher notes source exists",
        )

        check(
            teacher_notes is not None
            and teacher_notes.is_primary
            and teacher_notes.priority == 1,
            "Teacher notes are the primary source",
        )

        check(
            official_book is not None
            and not official_book.is_primary
            and official_book.priority == 2,
            "Official semester-one book has priority 2",
        )

        check(
            semester_two_book is not None
            and semester_two_book.priority == 100,
            "Semester-two book is inactive with priority 100",
        )

        for lesson in lessons:
            check(
                len(lesson.chunks) > 0,
                f"Lesson has chunks: {lesson.title}",
            )

        if teacher_notes is not None:
            check(
                len(teacher_notes.chunks) > 0,
                "Teacher notes contain chunks",
            )

            check(
                all(
                    chunk.lesson_id is not None
                    for chunk in teacher_notes.chunks
                ),
                "All teacher-note chunks are linked to lessons",
            )

        if official_book is not None:
            check(
                len(official_book.chunks) > 0,
                "Official book contains chunks",
            )

            check(
                all(
                    chunk.page_number is not None
                    for chunk in official_book.chunks
                ),
                "All official-book chunks have page numbers",
            )

        if semester_two_book is not None:
            check(
                len(semester_two_book.chunks) == 0,
                "Inactive semester-two book has no searchable chunks",
            )

        check(
            all(
                chunk.text.strip()
                for chunk in chunks
            ),
            "No empty chunks exist",
        )

        check(
            all(
                len(chunk.text_hash) == 64
                for chunk in chunks
            ),
            "All chunks have valid SHA-256 hashes",
        )

        for source in sources:
            source_path = (
                PROJECT_ROOT
                / source.stored_path
            )

            check(
                source_path.exists(),
                f"Source file exists: {source.original_filename}",
            )

        embedded_count = (
            ContentChunk.query
            .filter(
                ContentChunk.embedding.isnot(None)
            )
            .count()
        )

        print("-" * 60)
        print(f"Curricula: {len(curricula)}")
        print(f"Units: {len(units)}")
        print(f"Lessons: {len(lessons)}")
        print(f"Sources: {len(sources)}")
        print(f"Chunks: {len(chunks)}")
        print(f"Embeddings currently generated: {embedded_count}")

        check(
            embedded_count == 0,
            "Embeddings are correctly waiting for phase two",
        )

        print("=" * 60)

        if failures:
            print(
                f"Verification failed: "
                f"{len(failures)} problem(s)."
            )
            raise SystemExit(1)

        print(
            "Knowledge preparation verification passed."
        )


if __name__ == "__main__":
    verify()