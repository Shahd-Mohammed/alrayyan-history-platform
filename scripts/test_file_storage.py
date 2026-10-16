from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from app import app
from alrayyan.routes.learning import build_concept_map_svg
from alrayyan.services.file_storage import resolve_stored_file, upload_to_object_storage


def run_tests():
    original_upload_folder = app.config["UPLOAD_FOLDER"]
    with TemporaryDirectory() as temporary_folder:
        root = Path(temporary_folder)
        app.config["UPLOAD_FOLDER"] = str(root)
        try:
            with app.app_context():
                sample = root / "worksheets" / "sample.pdf"
                sample.parent.mkdir(parents=True)
                sample.write_bytes(b"%PDF-test")

                resolved = resolve_stored_file("worksheets/sample.pdf")
                assert isinstance(resolved, Path)
                assert resolved == sample.resolve()
                assert resolved.read_bytes() == b"%PDF-test"
                assert resolve_stored_file("worksheets/missing.pdf") is None

                remote_settings = {
                    "bucket": "test-bucket",
                    "access_key": "test-access",
                    "secret_key": "test-secret",
                    "endpoint_url": None,
                    "region": "us-east-1",
                }
                fake_client = SimpleNamespace(
                    get_object=lambda **kwargs: {
                        "Body": BytesIO(b"durable-file-content")
                    }
                )
                with patch(
                    "alrayyan.services.file_storage._storage_settings",
                    return_value=remote_settings,
                ), patch(
                    "alrayyan.services.file_storage._client",
                    return_value=fake_client,
                ):
                    remote_file = resolve_stored_file("worksheets/remote.pdf")
                    assert remote_file.read() == b"durable-file-content"

                try:
                    resolve_stored_file("../outside.pdf")
                except ValueError:
                    pass
                else:
                    raise AssertionError("Path traversal should be rejected")

                original_require_durable = app.config.get("REQUIRE_DURABLE_UPLOADS", False)
                app.config["REQUIRE_DURABLE_UPLOADS"] = True
                try:
                    with patch(
                        "alrayyan.services.file_storage._storage_settings",
                        return_value=None,
                    ):
                        try:
                            upload_to_object_storage(sample, "worksheets/sample.pdf")
                        except RuntimeError as error:
                            assert "التخزين الدائم" in str(error)
                        else:
                            raise AssertionError(
                                "Production upload must fail when durable storage is missing"
                            )
                finally:
                    app.config["REQUIRE_DURABLE_UPLOADS"] = original_require_durable

                concept_map = SimpleNamespace(
                    id=1,
                    title="خريطة الاستعمار",
                    nodes=[
                        SimpleNamespace(
                            id=1,
                            position_x=0,
                            position_y=0,
                            label="الاستعمار",
                            description="السيطرة على أرض وشعب",
                        ),
                        SimpleNamespace(
                            id=2,
                            position_x=300,
                            position_y=0,
                            label="المقاومة",
                            description="مواجهة السيطرة",
                        ),
                    ],
                    edges=[
                        SimpleNamespace(
                            source_node_id=1,
                            target_node_id=2,
                            label="أدى إلى",
                        )
                    ],
                )
                svg = build_concept_map_svg(concept_map)
                assert svg.startswith('<?xml version="1.0"')
                assert "<svg " in svg
                assert "خريطة الاستعمار" in svg
                assert "الاستعمار" in svg
                assert "المقاومة" in svg
                assert "أدى إلى" in svg
        finally:
            app.config["UPLOAD_FOLDER"] = original_upload_folder

    print("PASS: Local file resolution, path traversal protection, and concept-map export")


if __name__ == "__main__":
    run_tests()
