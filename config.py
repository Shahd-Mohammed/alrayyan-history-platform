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
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "0") == "1"
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE

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


    UPLOAD_FOLDER = os.getenv(
        "UPLOAD_FOLDER",
        "uploads",
    )

    MAX_CONTENT_LENGTH = int(
        os.getenv(
            "MAX_CONTENT_LENGTH",
            str(15 * 1024 * 1024),
        )
    )

    ALLOWED_WORKSHEET_EXTENSIONS = {
        "pdf",
        "doc",
        "docx",
        "png",
        "jpg",
        "jpeg",
    }


    SMTP_HOST = os.getenv("SMTP_HOST")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME = os.getenv("SMTP_USERNAME")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
    SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL")
    SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "1") == "1"
