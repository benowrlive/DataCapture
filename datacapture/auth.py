"""Authentication, sessions, and role/permission decorators."""
import functools
from urllib.parse import urlsplit
from flask import (Blueprint, render_template, request, redirect, url_for,
                   session, flash, abort, g)
from werkzeug.security import generate_password_hash, check_password_hash
from .db import q, x, audit

bp = Blueprint("auth", __name__)

ROLES = ("admin", "data_entry", "read_only")
ROLE_LABELS = {"admin": "Project Admin", "data_entry": "Data Entry",
               "read_only": "Read Only"}


# ---------------------------------------------------------------- helpers

def current_user():
    uid = session.get("user_id")
    if uid is None:
        return None
    return q("SELECT * FROM users WHERE id=? AND active=1", (uid,), one=True)


def login_required(view):
    @functools.wraps(view)
    def wrapped(*a, **kw):
        user = current_user()
        if user is None:
            return redirect(url_for("auth.login", next=request.path))
        g.user = user
        return view(*a, **kw)
    return wrapped


def admin_required(view):
    @functools.wraps(view)
    def wrapped(*a, **kw):
        user = current_user()
        if user is None:
            return redirect(url_for("auth.login", next=request.path))
        if not user["is_admin"]:
            abort(403)
        g.user = user
        return view(*a, **kw)
    return wrapped


def project_role(project_id):
    """Role of current user in a project. Global admins are always admin."""
    user = current_user()
    if user is None:
        return None
    if user["is_admin"]:
        return "admin"
    row = q("SELECT role FROM project_users WHERE project_id=? AND user_id=?",
            (project_id, user["id"]), one=True)
    return row["role"] if row else None


def project_access(min_role="read_only"):
    """Decorator for views taking pid as first kwarg; checks membership."""
    order = {"read_only": 0, "data_entry": 1, "admin": 2}

    def deco(view):
        @functools.wraps(view)
        def wrapped(pid, *a, **kw):
            user = current_user()
            if user is None:
                return redirect(url_for("auth.login", next=request.path))
            g.user = user
            role = project_role(pid)
            if role is None or order[role] < order[min_role]:
                abort(403)
            g.role = role
            project = q("SELECT * FROM projects WHERE id=?", (pid,), one=True)
            if project is None:
                abort(404)
            g.project = project
            return view(pid, *a, **kw)
        return wrapped
    return deco


def hash_pw(pw):
    return generate_password_hash(pw, method="pbkdf2:sha256")


def safe_next_url(target):
    if not target or not target.startswith("/") or target.startswith("//"):
        return None
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc:
        return None
    return target


# ---------------------------------------------------------------- routes

@bp.route("/setup", methods=["GET", "POST"])
def first_run():
    """First-run wizard: create the initial administrator account."""
    if q("SELECT id FROM users LIMIT 1", one=True):
        return redirect(url_for("auth.login"))
    error = None
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "")
        n = request.form.get("display_name", "").strip() or u
        if len(u) < 3 or len(p) < 8:
            error = "Username must be ≥3 chars and password ≥8 chars."
        else:
            x("INSERT INTO users (username, password_hash, display_name, is_admin)"
              " VALUES (?,?,?,1)", (u, hash_pw(p), n))
            audit("user.create", details=f"first-run admin '{u}'", username=u)
            flash("Administrator account created. Please log in.")
            return redirect(url_for("auth.login"))
    return render_template("setup.html", error=error)


@bp.route("/forgot-password")
def forgot_password():
    return render_template("forgot_password.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if not q("SELECT id FROM users LIMIT 1", one=True):
        return redirect(url_for("auth.first_run"))
    error = None
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "")
        user = q("SELECT * FROM users WHERE username=? AND active=1", (u,), one=True)
        if user and check_password_hash(user["password_hash"], p):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            audit("login", username=u)
            return redirect(safe_next_url(request.args.get("next"))
                            or url_for("projects.home"))
        error = "Invalid username or password."
        audit("login.failed", details=f"username '{u}'", username=u or "?")
    return render_template("login.html", error=error)


@bp.route("/logout")
def logout():
    if session.get("username"):
        audit("logout")
    session.clear()
    return redirect(url_for("auth.login"))
