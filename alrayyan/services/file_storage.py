"""Local and S3-compatible object storage for user-uploaded learning files.

Set S3_BUCKET, S3_ACCESS_KEY_ID, and S3_SECRET_ACCESS_KEY to enable durable
object storage. S3_ENDPOINT_URL is optional (for example, an S3-compatible
provider); S3_REGION defaults to "auto".
"""
from io import BytesIO
import os
from pathlib import Path

from flask import current_app


def _storage_settings():
    bucket = (os.getenv("S3_BUCKET") or "").strip()
    access_key = (os.getenv("S3_ACCESS_KEY_ID") or "").strip()
    secret_key = (os.getenv("S3_SECRET_ACCESS_KEY") or "").strip()
    endpoint_url = (os.getenv("S3_ENDPOINT_URL") or "").strip() or None
    region = (os.getenv("S3_REGION") or "auto").strip()

    configured = any((bucket, access_key, secret_key, endpoint_url))
    if not configured:
        return None

    if not all((bucket, access_key, secret_key)):
        raise RuntimeError(
            "Object storage needs S3_BUCKET, S3_ACCESS_KEY_ID, and "
            "S3_SECRET_ACCESS_KEY."
        )

    return {
        "bucket": bucket,
        "access_key": access_key,
        "secret_key": secret_key,
        "endpoint_url": endpoint_url,
        "region": region,
    }


def object_storage_enabled():
    return _storage_settings() is not None


def _client(settings):
    try:
        import boto3
    except ImportError as error:
        raise RuntimeError(
            "Install boto3 to use configured object storage."
        ) from error

    options = {
        "aws_access_key_id": settings["access_key"],
        "aws_secret_access_key": settings["secret_key"],
        "region_name": settings["region"],
    }
    if settings["endpoint_url"]:
        options["endpoint_url"] = settings["endpoint_url"]
    return boto3.client("s3", **options)


def upload_to_object_storage(local_path, storage_key):
    """Copy an uploaded local file to durable storage when configured."""
    settings = _storage_settings()
    if settings is None:
        return False

    key = Path(str(storage_key)).as_posix().lstrip("/")
    if not key or key.startswith("../") or "/../" in key:
        raise ValueError("Invalid object-storage key.")

    try:
        _client(settings).upload_file(
            str(local_path),
            settings["bucket"],
            key,
        )
    except Exception as error:
        current_app.logger.exception(
            "Could not persist uploaded file to object storage: %s",
            key,
        )
        raise RuntimeError(
            "تعذر حفظ الملف في التخزين الدائم. لم يتم اعتماد عملية الرفع."
        ) from error
    return True


def resolve_stored_file(stored_path):
    """Return an existing local file or a BytesIO stream from object storage.

    Legacy absolute paths are accepted only when they resolve inside the
    configured uploads directory. Relative database paths are object keys.
    """
    if not stored_path:
        return None

    upload_root = Path(
        current_app.config["UPLOAD_FOLDER"]
    ).resolve()
    candidate = Path(str(stored_path))

    if candidate.is_absolute():
        candidate = candidate.resolve()
        try:
            relative_path = candidate.relative_to(upload_root)
        except ValueError as error:
            raise ValueError("Stored file path is outside the uploads folder.") from error
    else:
        candidate = (upload_root / candidate).resolve()
        try:
            relative_path = candidate.relative_to(upload_root)
        except ValueError as error:
            raise ValueError("Stored file path is outside the uploads folder.") from error

    if candidate.is_file():
        return candidate

    settings = _storage_settings()
    if settings is None:
        return None

    key = relative_path.as_posix()
    try:
        response = _client(settings).get_object(
            Bucket=settings["bucket"],
            Key=key,
        )
        content = response["Body"].read()
        return BytesIO(content)
    except Exception:
        current_app.logger.exception(
            "Stored file is missing locally and could not be fetched from object storage: %s",
            key,
        )
        return None
