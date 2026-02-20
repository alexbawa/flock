from celery import Celery, Task
from flask import Flask, jsonify


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object("app.config.Config")

    _init_celery(app)

    from app.db import close_db
    app.teardown_appcontext(close_db)

    from app.routes import jobs_bp
    app.register_blueprint(jobs_bp)

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"}), 200

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
    return celery_app
