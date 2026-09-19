from pathlib import Path

from dotenv import load_dotenv
from flask import Flask

from config import Config
from alrayyan.extensions import db, login_manager, migrate


def create_app():
    load_dotenv()

    app = Flask(__name__)
    app.config.from_object(Config)

    Path(app.instance_path).mkdir(
        parents=True,
        exist_ok=True
    )

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    from alrayyan.routes.main import main_bp
    app.register_blueprint(main_bp)

    return app