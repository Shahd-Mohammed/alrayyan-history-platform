"""Create the first platform administrator from environment variables.

This script only bootstraps an administrator when none exists. Once an admin
account exists, create additional admins through the protected admin UI.
"""
import os
import sys
from pathlib import Path

# Make the project root importable when this script is launched by file path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import app
from alrayyan.extensions import db
from alrayyan.models import User


def main():
    full_name = (os.getenv("INITIAL_ADMIN_NAME") or "مديرة منصة الريان").strip()
    email = (os.getenv("INITIAL_ADMIN_EMAIL") or "").strip().lower()
    password = os.getenv("INITIAL_ADMIN_PASSWORD") or ""

    if not email or email.count("@") != 1 or "." not in email.rsplit("@", 1)[-1]:
        raise SystemExit("Set INITIAL_ADMIN_EMAIL to a valid email address.")
    if len(password) < 12 or len(password) > 128:
        raise SystemExit("Set INITIAL_ADMIN_PASSWORD to 12–128 characters.")
    if len(full_name) < 2 or len(full_name) > 150:
        raise SystemExit("INITIAL_ADMIN_NAME must be 2–150 characters.")

    with app.app_context():
        if User.query.filter_by(role="admin").first():
            raise SystemExit(
                "An administrator already exists. Use the protected admin UI "
                "to create additional administrator accounts."
            )

        existing = User.query.filter_by(email=email).first()
        if existing:
            raise SystemExit(
                "That email already belongs to an account. No account was changed."
            )

        account = User(
            full_name=full_name,
            email=email,
            role="admin",
            is_active_account=True,
        )
        account.set_password(password)
        db.session.add(account)
        db.session.commit()
        print(f"Created the initial administrator account for {email}.")


if __name__ == "__main__":
    main()
