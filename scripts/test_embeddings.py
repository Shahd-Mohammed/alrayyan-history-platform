import sys

from alrayyan.services.embeddings import (
    generate_embeddings,
    get_embedding_settings,
)


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def test():
    settings = get_embedding_settings()

    test_texts = [
        "ما المقصود بالاستعمار؟",
        "ما دوافع الاستعمار الأوروبي؟",
    ]

    vectors = generate_embeddings(
        test_texts
    )

    print(
        f"Model: {settings['model']}"
    )
    print(
        f"Returned vectors: {len(vectors)}"
    )
    print(
        f"Embedding dimension: {len(vectors[0])}"
    )
    print(
        f"First five values: {vectors[0][:5]}"
    )

    if len(vectors) != len(test_texts):
        raise RuntimeError(
            "Embedding count test failed."
        )

    if len(vectors[0]) == 0:
        raise RuntimeError(
            "Embedding vector is empty."
        )

    print(
        "Embedding connection test passed."
    )


if __name__ == "__main__":
    test()