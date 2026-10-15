import json
import math
import re
import unicodedata

from flask import current_app

from alrayyan.models import (
    ContentChunk,
    Curriculum,
    SourceDocument,
)
from alrayyan.services.embeddings import (
    generate_embeddings,
    get_embedding_settings,
)


def cosine_similarity(vector_a, vector_b):
    """
    Calculate semantic similarity between two vectors.
    """
    if len(vector_a) != len(vector_b):
        raise ValueError(
            "Embedding dimensions do not match."
        )

    dot_product = sum(
        value_a * value_b
        for value_a, value_b
        in zip(vector_a, vector_b)
    )

    norm_a = math.sqrt(
        sum(value * value for value in vector_a)
    )

    norm_b = math.sqrt(
        sum(value * value for value in vector_b)
    )

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (norm_a * norm_b)


def get_source_bonus(source):
    """
    Apply a small ranking bonus without overriding
    semantic relevance.

    Teacher notes remain preferred when results
    are similarly relevant.
    """
    if source.is_primary:
        return 0.025

    if source.priority == 2:
        return 0.010

    return 0.0


def format_citation(source, page_number):
    """
    Return a readable Arabic source citation.
    """
    if page_number is not None:
        return (
            f"{source.title}، "
            f"صفحة {page_number}"
        )

    return source.title


def _normalize_keyword_text(value):
    value = unicodedata.normalize("NFKC", value or "").casefold()
    value = re.sub(r"[\u064B-\u065F\u0670]", "", value)
    return value.translate(str.maketrans({
        "أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه",
    }))


def keyword_search_fallback(query, top_k=5, lesson_id=None):
    """Retrieve relevant curriculum passages when embedding search is unavailable."""
    terms = [
        token for token in re.findall(r"\w+", _normalize_keyword_text(query))
        if len(token) > 1
    ]
    unique_terms = list(dict.fromkeys(terms))
    if not unique_terms:
        return []

    candidate_query = (
        ContentChunk.query
        .join(SourceDocument, ContentChunk.source_id == SourceDocument.id)
        .join(Curriculum, SourceDocument.curriculum_id == Curriculum.id)
        .filter(
            Curriculum.is_active.is_(True),
            SourceDocument.is_active.is_(True),
            ContentChunk.text.isnot(None),
        )
    )
    if lesson_id is not None:
        candidate_query = candidate_query.filter(ContentChunk.lesson_id == lesson_id)

    results = []
    for chunk in candidate_query.all():
        normalized_text = _normalize_keyword_text(chunk.text)
        matched_terms = [
            term for term in unique_terms if term in normalized_text
        ]
        if not matched_terms:
            continue

        source = chunk.source
        coverage = len(matched_terms) / len(unique_terms)
        frequency_bonus = min(
            0.05,
            sum(normalized_text.count(term) for term in matched_terms) * 0.005,
        )
        similarity = min(1.0, coverage + frequency_bonus)
        results.append({
            "chunk_id": chunk.id,
            "text": chunk.text,
            "similarity": similarity,
            "ranking_score": similarity + get_source_bonus(source),
            "source_id": source.id,
            "source_title": source.title,
            "source_type": source.source_type,
            "source_priority": source.priority,
            "is_primary": source.is_primary,
            "page_number": chunk.page_number,
            "lesson_id": chunk.lesson_id,
            "lesson_title": chunk.lesson.title if chunk.lesson else None,
            "citation": format_citation(source, chunk.page_number),
        })

    results.sort(key=lambda item: item["ranking_score"], reverse=True)
    return results[:top_k]


def semantic_search(
    query,
    top_k=5,
    min_similarity=0.15,
    lesson_id=None,
):
    """
    Search active curriculum chunks using cosine similarity.
    """
    if not query or not query.strip():
        raise ValueError(
            "Search query cannot be empty."
        )

    try:
        settings = get_embedding_settings()
        query_vector = generate_embeddings(
            query.strip()
        )[0]
    except Exception as error:
        current_app.logger.warning(
            "Embedding search unavailable; using curriculum keyword fallback: %s",
            error,
        )
        return keyword_search_fallback(
            query,
            top_k=top_k,
            lesson_id=lesson_id,
        )

    candidate_query = (
        ContentChunk.query
        .join(
            SourceDocument,
            ContentChunk.source_id
            == SourceDocument.id,
        )
        .join(
            Curriculum,
            SourceDocument.curriculum_id
            == Curriculum.id,
        )
        .filter(
            Curriculum.is_active.is_(True),
            SourceDocument.is_active.is_(True),
            ContentChunk.embedding.isnot(None),
            ContentChunk.embedding_model
            == settings["model"],
        )
    )

    if lesson_id is not None:
        candidate_query = candidate_query.filter(
            ContentChunk.lesson_id == lesson_id
        )

    candidates = candidate_query.all()

    results = []

    for chunk in candidates:
        stored_vector = json.loads(
            chunk.embedding
        )

        similarity = cosine_similarity(
            query_vector,
            stored_vector,
        )

        if similarity < min_similarity:
            continue

        source = chunk.source
        source_bonus = get_source_bonus(source)
        ranking_score = similarity + source_bonus

        results.append(
            {
                "chunk_id": chunk.id,
                "text": chunk.text,
                "similarity": similarity,
                "ranking_score": ranking_score,
                "source_id": source.id,
                "source_title": source.title,
                "source_type": source.source_type,
                "source_priority": source.priority,
                "is_primary": source.is_primary,
                "page_number": chunk.page_number,
                "lesson_id": chunk.lesson_id,
                "lesson_title": (
                    chunk.lesson.title
                    if chunk.lesson
                    else None
                ),
                "citation": format_citation(
                    source,
                    chunk.page_number,
                ),
            }
        )

    results.sort(
        key=lambda item: item["ranking_score"],
        reverse=True,
    )

    return results[:top_k]
