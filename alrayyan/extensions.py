from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect


db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()

@login_manager.user_loader
@login_manager.user_loader
def load_user(user_id):
    from alrayyan.models import User

    try:
        parsed_user_id = int(user_id)
    except (TypeError, ValueError):
        return None

    return db.session.get(
        User,
        parsed_user_id,
    )
    
login_manager.login_view = "auth.login"
login_manager.login_message = (
    "يرجى تسجيل الدخول للوصول إلى هذه الصفحة."
)
login_manager.login_message_category = "info"