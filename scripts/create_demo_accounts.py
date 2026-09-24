
import os

from app import app

from alrayyan.extensions import db
from alrayyan.models import User


ACCOUNTS = [
    {
        "full_name": "معلمة الريان",
        "email": "teacher@alrayyan.local",
        "password": os.getenv("DEMO_TEACHER_PASSWORD"),
        "role": "teacher",
    },
    {
        "full_name": "طالب تجريبي",
        "email": "student@alrayyan.local",
        "password": os.getenv("DEMO_STUDENT_PASSWORD"),
        "role": "student",
    },
]


def main():
    with app.app_context():
        for account in ACCOUNTS:
            user = User.query.filter_by(
                email=account["email"],
            ).first()

            if user:
                print(
                    "Account already exists: "
                    f"{account['email']}"
                )
                continue

            user = User(
                full_name=account["full_name"],
                email=account["email"],
                role=account["role"],
            )

            user.set_password(
                account["password"]
            )

            db.session.add(user)

            print(
                "Created account: "
                f"{account['email']}"
            )

        db.session.commit()

        print("-" * 55)
        print("Demo accounts are ready.")


if __name__ == "__main__":
    main()

