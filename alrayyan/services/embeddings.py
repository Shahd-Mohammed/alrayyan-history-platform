import os
import time

import requests
from dotenv import load_dotenv


load_dotenv()


class EmbeddingError(RuntimeError):
    """
    Raised when the embedding provider cannot return
    a valid result.
    """


def get_embedding_settings():
    api_key = os.getenv("OPENROUTER_API_KEY")
    model = os.getenv(
        "EMBEDDING_MODEL",
        "openai/text-embedding-3-small",
    )
    api_url = os.getenv(
        "EMBEDDING_API_URL",
        "https://openrouter.ai/api/v1/embeddings",
    )

    if not api_key:
        raise EmbeddingError(
            "OPENROUTER_API_KEY is missing from .env"
        )

    return {
        "api_key": api_key,
        "model": model,
        "api_url": api_url,
    }


def generate_embeddings(
    texts,
    max_retries=4,
    timeout=120,
):
    """
    Generate embeddings for one or multiple texts.

    The function never prints or returns the API key.
    """
    if isinstance(texts, str):
        texts = [texts]

    cleaned_texts = [
        text.strip()
        for text in texts
        if text and text.strip()
    ]

    if not cleaned_texts:
        raise ValueError(
            "At least one non-empty text is required."
        )

    settings = get_embedding_settings()

    headers = {
        "Authorization": (
            f"Bearer {settings['api_key']}"
        ),
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:5000",
        "X-Title": "Al-Rayyan History Platform",
    }

    payload = {
        "model": settings["model"],
        "input": cleaned_texts,
        "encoding_format": "float",
    }

    retryable_status_codes = {
        408,
        429,
        500,
        502,
        503,
        524,
        529,
    }

    for attempt in range(1, max_retries + 1):
        try:
            response = requests.post(
                settings["api_url"],
                headers=headers,
                json=payload,
                timeout=timeout,
            )

        except requests.RequestException as error:
            if attempt == max_retries:
                raise EmbeddingError(
                    "Could not connect to the "
                    "embedding provider."
                ) from error

            time.sleep(2 ** (attempt - 1))
            continue

        if response.status_code == 200:
            result = response.json()
            data = result.get("data", [])

            ordered_data = sorted(
                data,
                key=lambda item: item["index"],
            )

            embeddings = [
                item["embedding"]
                for item in ordered_data
            ]

            if len(embeddings) != len(cleaned_texts):
                raise EmbeddingError(
                    "The provider returned an unexpected "
                    "number of embeddings."
                )

            if not embeddings or not embeddings[0]:
                raise EmbeddingError(
                    "The provider returned empty embeddings."
                )

            expected_dimension = len(embeddings[0])

            if not all(
                len(vector) == expected_dimension
                for vector in embeddings
            ):
                raise EmbeddingError(
                    "Embedding dimensions are inconsistent."
                )

            return embeddings

        if (
            response.status_code
            in retryable_status_codes
            and attempt < max_retries
        ):
            time.sleep(2 ** (attempt - 1))
            continue

        try:
            error_data = response.json()
            provider_message = (
                error_data.get("error", {})
                .get("message", response.text)
            )
        except ValueError:
            provider_message = response.text

        raise EmbeddingError(
            "Embedding request failed "
            f"with status {response.status_code}: "
            f"{provider_message[:300]}"
        )

    raise EmbeddingError(
        "Embedding generation failed."
    )