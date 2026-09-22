from pathlib import Path

from app import app
from alrayyan.models import User


def main():
    with app.app_context():
        student = User.query.filter_by(
            email="student@alrayyan.local"
        ).first()

        if student is None:
            raise RuntimeError(
                "Student account was not found."
            )

        client = app.test_client()

        with client.session_transaction() as session:
            session["_user_id"] = str(student.id)
            session["_fresh"] = True

        response = client.get(
            "/worksheets/1/download"
        )

        print("Status:", response.status_code)
        print(
            "Content-Type:",
            response.headers.get("Content-Type"),
        )
        print(
            "Content-Disposition:",
            response.headers.get(
                "Content-Disposition"
            ),
        )
        print(
            "Content-Length header:",
            response.headers.get(
                "Content-Length"
            ),
        )
        print(
            "Returned bytes:",
            len(response.data),
        )
        print(
            "First five bytes:",
            response.data[:5],
        )

        output_path = Path(
            "worksheet-download-test.pdf"
        )

        output_path.write_bytes(
            response.data
        )

        print(
            "Test file:",
            output_path.resolve(),
        )
        print(
            "Test file exists:",
            output_path.is_file(),
        )
        print(
            "Test file size:",
            output_path.stat().st_size,
        )


if __name__ == "__main__":
    main()