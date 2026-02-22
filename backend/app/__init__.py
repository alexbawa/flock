import logging
from urllib.parse import urlparse

from celery import Celery, Task
from flask import Flask, jsonify, request
from flask_cors import CORS

logger = logging.getLogger(__name__)


def create_app() -> Flask:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    app = Flask(__name__)
    app.config.from_object("app.config.Config")

    CORS(app)

    _init_celery(app)

    from app.db import close_db
    app.teardown_appcontext(close_db)

    from app.routes import jobs_bp
    app.register_blueprint(jobs_bp)

    @app.after_request
    def log_request(response):
        logger.info("%s %s %s", request.method, request.path, response.status_code)
        return response

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"}), 200

    logger.info("Flask app created")
    return app


def _init_celery(app: Flask) -> Celery:
    class FlaskTask(Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery_app = Celery(
        app.name,
        broker=app.config["REDIS_URL"],
        backend=app.config["REDIS_URL"],
        task_cls=FlaskTask,
    )
    celery_app.set_default()
    app.extensions["celery"] = celery_app

    parsed = urlparse(app.config["REDIS_URL"])
    logger.info("Celery initialized with broker %s://%s", parsed.scheme, parsed.hostname)
    return celery_app
