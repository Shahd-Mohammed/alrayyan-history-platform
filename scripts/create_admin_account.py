"""Create or promote the initial Alrayyan platform administrator.

Run from the project root with the app's configured database:
    python scripts/create_admin_account.py

The password is prompted without echo and is never written to source code.
For a deployed service, run this against the deployed database, not only the local DB.
"""
import getpass
import os

from app import app
from alrayyan.extensions import db
from alrayyan.models import User


DEFAULT_ADMIN_EMAIL = "1shahdmohammed@gmail.com"


def main():
    email = (os.getenv("ADMIN_EMAIL") or DEFAULT_ADMIN_EMAIL).strip().lower()
    full_name = (os.getenv("ADMIN_FULL_NAME") or "مديرة منصة الريان").strip()
    if not email or "@" not in email:
        raise SystemExit("ADMIN_EMAIL must be a valid email address.")

    password = os.getenv("ADMIN_PASSWORD")
    if not password:
        password = getpass.getpass("اختاري كلمة مرور قوية للأدمن (12 حرفًا على الأقل): ")
        confirmation = getpass.getpass("أعيدي كتابة كلمة المرور للتأكيد: ")
        if password != confirmation:
            raise SystemExit("كلمتا المرور غير متطابقتين؛ لم يتم إجراء أي تغيير.")

    if len(password) < 12:
        raise SystemExit("كلمة مرور الإدارة يجب أن تحتوي على 12 حرفًا على الأقل.")

    with app.app_context():
        user = User.query.filter_by(email=email).first()
        if user is not None and user.role != "admin":
            confirmation = input(
                f"البريد موجود بدور {user.role!r}. اكتبي PROMOTE فقط إذا كنتِ متأكدة من ترقية هذا الحساب: "
            ).strip()
            if confirmation != "PROMOTE":
                raise SystemExit("أُلغيت العملية دون تغيير الحساب.")

        if user is None:
            user = User(full_name=full_name, email=email, role="admin", is_active_account=True)
            db.session.add(user)
        else:
            user.full_name = full_name or user.full_name
            user.role = "admin"
            user.is_active_account = True

        user.set_password(password)
        db.session.commit()
        print(f"تم تجهيز حساب الإدارة: {email}")
        print("لم تتم طباعة كلمة المرور أو حفظها داخل ملفات المشروع.")


if __name__ == "__main__":
    main()
