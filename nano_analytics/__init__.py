import os
from flask import Flask
from .db import init_db, close_db
from .routes import bp


def create_app(config=None):
    """Application factory. Call as: flask --app 'nano_analytics:create_app()' run"""
    app = Flask(
        __name__,
        static_folder=os.path.join(os.path.dirname(__file__), "..", "static"),
        template_folder=os.path.join(os.path.dirname(__file__), "..", "templates"),
    )

    app.config["DB_PATH"]  = os.environ.get("DB_PATH", "/data/analytics.db")
    app.config["BASE_URL"] = os.environ.get("BASE_URL", "")

    if config:
        app.config.update(config)

    app.teardown_appcontext(close_db)
    app.register_blueprint(bp)
    init_db(app)

    return app
