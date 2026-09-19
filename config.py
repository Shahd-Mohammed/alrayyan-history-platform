import os


class Config:
    SECRET_KEY = os.getenv(
        "SECRET_KEY",
        "development-secret-key"
    )

    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "sqlite:///alrayyan.db"
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

    OPENROUTER_MODEL = os.getenv(
        "OPENROUTER_MODEL",
        "openai/gpt-4o-mini"
    )

    EMBEDDING_MODEL = os.getenv(
        "EMBEDDING_MODEL",
        "openai/text-embedding-3-small"
    )