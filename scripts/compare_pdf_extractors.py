import sys
from pathlib import Path

import pymupdf
from pypdf import PdfReader


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


project_root = Path(__file__).resolve().parents[1]
official_folder = (
    project_root
    / "curriculum"
    / "raw"
    / "official"
)

pdf_files = list(official_folder.glob("*.pdf"))

if not pdf_files:
    print("No official PDF was found.")
    raise SystemExit(1)


pdf_path = pdf_files[0]

print(f"Testing: {pdf_path.name}")
print("=" * 70)


pypdf_reader = PdfReader(str(pdf_path))
pypdf_text = "\n".join(
    page.extract_text() or ""
    for page in pypdf_reader.pages
)

print("PyPDF result")
print(f"Characters: {len(pypdf_text):,}")
print(f"Preview: {pypdf_text[:500]}")
print()


fitz_document = pymupdf.open(str(pdf_path))
fitz_text = "\n".join(
    page.get_text("text")
    for page in fitz_document
)

print("=" * 70)
print("PyMuPDF result")
print(f"Characters: {len(fitz_text):,}")
print(f"Preview: {fitz_text[:500]}")
print()


if len(fitz_text) > len(pypdf_text):
    print("Recommended extractor: PyMuPDF")
else:
    print("Recommended extractor: PyPDF")