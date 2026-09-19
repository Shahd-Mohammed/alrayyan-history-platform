import sys

from alrayyan import create_app
from alrayyan.services.semantic_search import (
    semantic_search,
)


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


TEST_QUESTIONS = [
    "ما المقصود بالاستعمار وما دوافعه؟",
    "كيف فرض الانتداب الفرنسي على سوريا ولبنان؟",
    "اشرح الاستعمار الاستيطاني في الجزائر",
]


def print_result(position, result):
    preview = result["text"][:280].replace(
        "\n",
        " ",
    )

    print(f"Result {position}")
    print(
        f"Similarity: "
        f"{result['similarity']:.4f}"
    )
    print(
        f"Ranking score: "
        f"{result['ranking_score']:.4f}"
    )
    print(
        f"Source: "
        f"{result['citation']}"
    )
    print(
        f"Primary: "
        f"{result['is_primary']}"
    )
    print(
        f"Priority: "
        f"{result['source_priority']}"
    )
    print(
        f"Lesson: "
        f"{result['lesson_title']}"
    )
    print(f"Text: {preview}")
    print("-" * 60)


def run_tests():
    app = create_app()

    with app.app_context():
        for question in TEST_QUESTIONS:
            print("=" * 70)
            print(f"Question: {question}")
            print("=" * 70)

            results = semantic_search(
                question,
                top_k=3,
            )

            if not results:
                raise RuntimeError(
                    "Semantic search returned no results."
                )

            for position, result in enumerate(
                results,
                start=1,
            ):
                print_result(
                    position,
                    result,
                )

        print("=" * 70)
        print(
            "Semantic search tests passed."
        )


if __name__ == "__main__":
    run_tests()