import hashlib
import re


def clean_arabic_text(text):
    """
    Apply conservative cleaning without changing
    the historical meaning of the source.
    """
    if not text:
        return ""

    replacements = {
        "\ufeff": "",
        "\u200b": "",
        "\u200c": "",
        "\u200d": "",
        "\ufffd": "",
        "āأ": "أ",
        "āإ": "إ",
        "āا": "ا",
        "الԽ": "ال",
        "الҙ": "ال",
    }

    for old_value, new_value in replacements.items():
        text = text.replace(
            old_value,
            new_value,
        )

    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")

    text = re.sub(
        r"[ \t]+",
        " ",
        text,
    )

    text = re.sub(
        r"\n[ \t]+",
        "\n",
        text,
    )

    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text,
    )

    return text.strip()


def create_text_hash(text):
    """
    Create a fingerprint for one text chunk.
    """
    normalized = clean_arabic_text(text)

    return hashlib.sha256(
        normalized.encode("utf-8")
    ).hexdigest()


def chunk_text(
    text,
    max_words=220,
    overlap_words=35,
):
    """
    Split text into overlapping chunks.

    Overlap preserves context between consecutive chunks.
    """
    cleaned_text = clean_arabic_text(text)
    words = cleaned_text.split()

    if not words:
        return []

    if overlap_words >= max_words:
        raise ValueError(
            "overlap_words must be smaller than max_words"
        )

    chunks = []
    start = 0
    step = max_words - overlap_words

    while start < len(words):
        end = min(
            start + max_words,
            len(words),
        )

        chunk = " ".join(
            words[start:end]
        ).strip()

        if chunk:
            chunks.append(chunk)

        if end >= len(words):
            break

        start += step

    return chunks