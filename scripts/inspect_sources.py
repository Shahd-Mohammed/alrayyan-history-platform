import sys
from pathlib import Path

from alrayyan.services.document_reader import inspect_document


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


project_root = Path(__file__).resolve().parents[1]
sources_folder = project_root / "curriculum" / "raw"

supported_files = sorted(
    file_path
    for file_path in sources_folder.rglob("*")
    if file_path.suffix.lower() in {".pdf", ".docx"}
)


if not supported_files:
    print("No PDF or DOCX sources were found.")
    raise SystemExit(1)


print(f"Found {len(supported_files)} source file(s).\n")


for file_path in supported_files:
    try:
        information = inspect_document(file_path)

        print("=" * 70)
        print(f"File: {information['filename']}")
        print(f"Type: {information['extension']}")
        print(f"Pages: {information['page_count']}")
        print(
            f"Characters: "
            f"{information['character_count']:,}"
        )
        print(f"Checksum: {information['checksum']}")
        print(f"Preview: {information['text_preview']}")
        print()

    except Exception as error:
        print("=" * 70)
        print(f"Could not read: {file_path.name}")
        print(f"Reason: {error}")
        print()