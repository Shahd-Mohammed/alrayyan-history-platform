"""Create the first platform administrator once, from a trusted local shell.

Set INITIAL_ADMIN_NAME, INITIAL_ADMIN_EMAIL, and INITIAL_ADMIN_PASSWORD in the
environment before running this script. It deliberately refuses to create or
promote accounts if any administrator already exists.
"""
import os
import re
import sys

from app import app
from alrayyan.extensions import db
from alrayyan.models import User


def main():
    full_name = (os.environ.get("INITIAL_ADMIN_NAME") or "").strip()
    email = (os.environ.get("INITIAL_ADMIN_EMAIL") or "").strip().lower()
    password = os.environ.get("INITIAL_ADMIN_PASSWORD") or ""

    if not full_name or len(full_name) < 2 or len(full_name) > 150:
        sys.exit("Set INITIAL_ADMIN_NAME to a valid full name.")
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or len(email) > 255:
        sys.exit("Set INITIAL_ADMIN_EMAIL to a valid email address.")
    if len(password) < 16 or len(password) > 128:
        sys.exit("INITIAL_ADMIN_PASSWORD must be between 16 and 128 characters.")
    if password.lower() in {email.lower(), full_name.lower()}:
        sys.exit("Choose a unique password that is not your name or email.")

    with app.app_context():
        if User.query.filter_by(role="admin").first():
            sys.exit("An administrator already exists; no account was changed.")
        if User.query.filter_by(email=email).first():
            sys.exit("That email already belongs to an account; no account was changed.")

        account = User(
            full_name=full_name,
            email=email,
            role="admin",
            is_active_account=True,
        )
        account.set_password(password)
        db.session.add(account)
        db.session.commit()
        print(f"First administrator created successfully: {email}")
        print("Remove the INITIAL_ADMIN_* environment variables from this shell now.")


if __name__ == "__main__":
    main()
