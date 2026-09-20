from app import app

from alrayyan.services.ai_teacher import ask_ai_teacher


QUESTION = "ما المقصود بالاستعمار وما أهم دوافعه؟"


def main():
    with app.app_context():
        print("=" * 70)
        print("Question:")
        print(QUESTION)
        print("=" * 70)

        result = ask_ai_teacher(QUESTION)

        print("Answer:")
        print(result["answer"])

        print("\nSources:")

        for index, source in enumerate(
            result["sources"],
            start=1,
        ):
            print("-" * 70)
            print(f"Source {index}: {source['title']}")

            if source["lesson_title"]:
                print(
                    f"Lesson: {source['lesson_title']}"
                )

            if source["page_number"] is not None:
                print(
                    f"Page: {source['page_number']}"
                )

            print(
                f"Primary: {source['is_primary']}"
            )
            print(
                f"Similarity: {source['similarity']}"
            )

        print("=" * 70)
        print("AI teacher test passed.")


if __name__ == "__main__":
    main()