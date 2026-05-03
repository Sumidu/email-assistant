import os

from flask import Flask, render_template


def create_app(base_dir: str) -> Flask:
    from app.routes.accounts import bp as accounts_bp
    from app.routes.chat import bp as chat_bp
    from app.routes.calendar import bp as calendar_bp
    from app.routes.config import bp as config_bp
    from app.routes.emails import bp as emails_bp
    from app.routes.folders import bp as folders_bp
    from app.routes.knowledge import bp as knowledge_bp
    from app.routes.logs import bp as logs_bp
    from app.routes.system import bp as system_bp
    from app.routes.tasks import bp as tasks_bp
    from app.routes.todos import bp as todos_bp

    app = Flask(
        __name__,
        template_folder=os.path.join(base_dir, "templates"),
        static_folder=os.path.join(base_dir, "static"),
    )

    @app.route("/")
    def index():
        return render_template("index.html")

    for bp in (
        accounts_bp,
        folders_bp,
        emails_bp,
        tasks_bp,
        knowledge_bp,
        config_bp,
        calendar_bp,
        chat_bp,
        logs_bp,
        system_bp,
        todos_bp,
    ):
        app.register_blueprint(bp)

    return app
