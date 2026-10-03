from pathlib import Path

from dotenv import load_dotenv
from flask import Flask


load_dotenv()


from config import Config

from alrayyan.extensions import (
    csrf,
    db,
    login_manager,
    migrate,
)


def create_app():
    app = Flask(__name__)

    app.config.from_object(
        Config
    )

    Path(
        app.instance_path
    ).mkdir(
        parents=True,
        exist_ok=True,
    )

    Path(
        app.config["UPLOAD_FOLDER"]
    ).mkdir(
        parents=True,
        exist_ok=True,
    )

    db.init_app(app)
    csrf.init_app(app)

    migrate.init_app(
        app,
        db,
        render_as_batch=True,
    )

    login_manager.init_app(app)

    from alrayyan import models

    from alrayyan.routes.assessment import (
        assessment_bp,
    )

    from alrayyan.routes.auth import (
        auth_bp,
    )

    from alrayyan.routes.main import (
        main_bp,
    )

    from alrayyan.routes.teacher import (
        teacher_bp,
    )

    from alrayyan.routes.teacher_dashboard import (
        teacher_dashboard_bp,
    )

    from alrayyan.routes.worksheets import (
        worksheets_bp,
    )

    from alrayyan.routes.challenges import (
        challenges_bp,
    )
    from alrayyan.routes.platform_admin import platform_admin_bp
    from alrayyan.routes.learning import learning_bp
    from alrayyan.routes.worksheet_center import worksheet_center_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(teacher_bp)
    app.register_blueprint(auth_bp)

    app.register_blueprint(
        teacher_dashboard_bp
    )

    app.register_blueprint(
        worksheets_bp
    )

    app.register_blueprint(
        assessment_bp
    )

    app.register_blueprint(
        challenges_bp
    )
    app.register_blueprint(platform_admin_bp)
    app.register_blueprint(learning_bp)
    app.register_blueprint(worksheet_center_bp)

    @app.context_processor
    def platform_context():
        from alrayyan.models import PlatformSettings
        try:
            settings = PlatformSettings.get_or_create()
        except Exception:
            settings = None
        return {"platform_settings": settings}

    @app.after_request
    def secure_response_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), geolocation=()")
        return response

    return app
