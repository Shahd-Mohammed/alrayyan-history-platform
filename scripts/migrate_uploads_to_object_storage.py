"""Copy existing local uploads to configured S3-compatible durable storage.

Run from the project root after setting the S3_* environment variables.
This script never deletes or modifies local files.
"""
from pathlib import Path

from app import app
from alrayyan.services.file_storage import (
    object_storage_enabled,
    upload_to_object_storage,
)


def main():
    with app.app_context():
        if not object_storage_enabled():
            raise SystemExit(
                "Object storage is not configured. Set S3_BUCKET, "
                "S3_ACCESS_KEY_ID, and S3_SECRET_ACCESS_KEY first."
            )

        root = Path(app.config["UPLOAD_FOLDER"]).resolve()
        if not root.is_dir():
            raise SystemExit(f"Uploads folder not found: {root}")

        files = [
            path for path in root.rglob("*")
            if path.is_file() and path.name != ".gitkeep"
        ]
        uploaded = 0
        failed = 0

        for path in files:
            key = path.relative_to(root).as_posix()
            try:
                upload_to_object_storage(path, key)
                uploaded += 1
                print(f"Uploaded: {key}")
            except Exception as error:
                failed += 1
                print(f"FAILED: {key} ({error})")

        print(f"Finished. Uploaded: {uploaded}; failed: {failed}; total: {len(files)}")
        if failed:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
