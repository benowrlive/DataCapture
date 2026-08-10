"""DataCapture — a standalone REDCap-style data collection app."""
import os
import secrets
from flask import Flask, redirect, url_for, g

APP_VERSION = "1.2.0"


def create_app(data_dir=None):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    app = Flask("datacapture",
                template_folder=os.path.join(root, "templates"),
                static_folder=os.path.join(root, "static"))
    app.config["DATA_DIR"] = data_dir or os.path.join(root, "data")
    os.makedirs(app.config["DATA_DIR"], exist_ok=True)

    # persistent random secret key per install
    key_file = os.path.join(app.config["DATA_DIR"], "secret_key")
    if not os.path.exists(key_file):
        with open(key_file, "w") as f:
            f.write(secrets.token_hex(32))
    with open(key_file) as f:
        app.secret_key = f.read().strip()

    app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024  # 32 MB uploads

    # Pick up edited templates and static files without restarting the server.
    # Jinja re-reads a template whenever its file changes; cache headers are
    # disabled so browsers always fetch the newest CSS/JS after an update.
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
    app.jinja_env.auto_reload = True

    from . import db
    db.init_db(app)

    from . import auth, admin, projects, designer, events, records
    from . import surveys, importexport, reports, analysis
    app.register_blueprint(auth.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(projects.bp)
    app.register_blueprint(designer.bp)
    app.register_blueprint(events.bp)
    app.register_blueprint(records.bp)
    app.register_blueprint(surveys.bp)
    app.register_blueprint(importexport.bp)
    app.register_blueprint(reports.bp)
    app.register_blueprint(analysis.bp)

    @app.route("/")
    def index():
        return redirect(url_for("projects.home"))

    @app.context_processor
    def inject_globals():
        from .auth import current_user, ROLE_LABELS
        from . import specialties as sp

        # The current project's specialty (if we're inside a project) drives the
        # Form Designer suggestion lists.
        proj = getattr(g, "project", None)
        specialty = ""
        if proj is not None:
            try:
                specialty = proj["specialty"] or ""
            except (KeyError, IndexError):
                specialty = ""

        def asset(filename):
            """Static URL stamped with the file's modified-time so browsers
            fetch the newest CSS/JS after an update — no hard refresh needed."""
            try:
                ver = int(os.path.getmtime(os.path.join(app.static_folder, filename)))
            except OSError:
                ver = 0
            return url_for("static", filename=filename) + "?v=" + str(ver)

        return {"current_user": current_user(), "APP_VERSION": APP_VERSION,
                "ROLE_LABELS": ROLE_LABELS, "asset": asset,
                "clinical_specialties": sp.specialties_list(),
                "instr_suggest_options": sp.instrument_suggestions(specialty),
                "field_suggest_options": sp.field_suggestions(specialty)}

    return app
