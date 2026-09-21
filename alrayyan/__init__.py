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
    app.config.from_object(Config)

    Path(
        app.instance_path
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

    app.register_blueprint(
        main_bp
    )

    app.register_blueprint(
        teacher_bp
    )

    app.register_blueprint(
        auth_bp
    )

    app.register_blueprint(
        teacher_dashboard_bp
    )

    return app