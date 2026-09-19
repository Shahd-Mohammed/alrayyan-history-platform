import os


class Config:
    SECRET_KEY = (
        os.getenv("SECRET_KEY")
        or "development-secret-key"
    )

    SQLALCHEMY_DATABASE_URI = (
        os.getenv("DATABASE_URL")
        or "sqlite:///alrayyan.db"
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    OPENROUTER_API_KEY = os.getenv(
        "OPENROUTER_API_KEY"
    )

    OPENROUTER_MODEL = (
        os.getenv("OPENROUTER_MODEL")
        or "openai/gpt-4o-mini"
    )

    EMBEDDING_MODEL = (
        os.getenv("EMBEDDING_MODEL")
        or "openai/text-embedding-3-small"
    )

    EMBEDDING_API_URL = (
        os.getenv("EMBEDDING_API_URL")
        or "https://openrouter.ai/api/v1/embeddings"
    )

    EMBEDDING_BATCH_SIZE = int(
        os.getenv("EMBEDDING_BATCH_SIZE")
        or "20"
    )