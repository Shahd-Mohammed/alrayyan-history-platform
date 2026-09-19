import json
import sys
from datetime import datetime, timezone

from alrayyan import create_app
from alrayyan.extensions import db
from alrayyan.models import (
    ContentChunk,
    Curriculum,
    SourceDocument,
)
from alrayyan.services.embeddings import (
    generate_embeddings,
    get_embedding_settings,
)


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def get_pending_chunks():
    """
    Return only chunks from active curricula and sources
    that do not already have embeddings.
    """
    return (
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
            ContentChunk.embedding.is_(None),
        )
        .order_by(ContentChunk.id)
        .all()
    )


def generate_all_embeddings():
    app = create_app()

    with app.app_context():
        settings = get_embedding_settings()

        batch_size = app.config[
            "EMBEDDING_BATCH_SIZE"
        ]

        pending_chunks = get_pending_chunks()
        total = len(pending_chunks)

        if total == 0:
            print(
                "No pending active chunks were found."
            )
            return

        print(
            f"Embedding model: "
            f"{settings['model']}"
        )
        print(
            f"Pending chunks: {total}"
        )
        print(
            f"Batch size: {batch_size}"
        )
        print("-" * 60)

        completed = 0

        for start in range(
            0,
            total,
            batch_size,
        ):
            batch = pending_chunks[
                start:start + batch_size
            ]

            texts = [
                chunk.text
                for chunk in batch
            ]

            try:
                vectors = generate_embeddings(
                    texts
                )

                for chunk, vector in zip(
                    batch,
                    vectors,
                ):
                    chunk.embedding = json.dumps(
                        vector,
                        separators=(",", ":"),
                    )

                    chunk.embedding_model = (
                        settings["model"]
                    )

                    chunk.embedding_dimensions = (
                        len(vector)
                    )

                    chunk.embedded_at = (
                        datetime.now(timezone.utc)
                    )

                db.session.commit()

            except Exception:
                db.session.rollback()
                print(
                    "Embedding generation stopped "
                    f"at chunk batch starting "
                    f"from position {start + 1}."
                )
                raise

            completed += len(batch)

            print(
                f"Completed: "
                f"{completed}/{total}"
            )

        print("=" * 60)
        print(
            "Embedding generation completed."
        )


if __name__ == "__main__":
    generate_all_embeddings()