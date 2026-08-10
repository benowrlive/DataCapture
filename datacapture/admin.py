"""Global administration: user accounts."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, g
from .db import q, x, audit
from .auth import admin_required, hash_pw

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("/users", methods=["GET", "POST"])
@admin_required
def users():
    if request.method == "POST":
        u = request.form.get("username", "").strip().lower()
        p = request.form.get("password", "")
        if len(u) < 3 or len(p) < 8:
            flash("Username must be ≥3 chars and password ≥8 chars.")
        elif q("SELECT id FROM users WHERE username=?", (u,), one=True):
            flash(f"Username '{u}' already exists.")
        else:
            x("INSERT INTO users (username, password_hash, display_name, email,"
              " is_admin) VALUES (?,?,?,?,?)",
              (u, hash_pw(p), request.form.get("display_name", "").strip() or u,
               request.form.get("email", "").strip(),
               1 if request.form.get("is_admin") else 0))
            audit("user.create", details=u)
            flash(f"User '{u}' created.")
        return redirect(url_for("admin.users"))
    all_users = q("SELECT * FROM users ORDER BY username")
    return render_template("admin_users.html", users=all_users)


@bp.route("/users/<int:uid>/toggle", methods=["POST"])
@admin_required
def toggle(uid):
    user = q("SELECT * FROM users WHERE id=?", (uid,), one=True)
    if user and user["id"] != g.user["id"]:
        x("UPDATE users SET active=? WHERE id=?", (0 if user["active"] else 1, uid))
        audit("user.toggle", details=f"{user['username']} active={not user['active']}")
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:uid>/password", methods=["POST"])
@admin_required
def reset_password(uid):
    user = q("SELECT * FROM users WHERE id=?", (uid,), one=True)
    p = request.form.get("password", "")
    if user and len(p) >= 8:
        x("UPDATE users SET password_hash=? WHERE id=?", (hash_pw(p), uid))
        audit("user.password_reset", details=user["username"])
        flash(f"Password reset for '{user['username']}'.")
    else:
        flash("Password must be at least 8 characters.")
    return redirect(url_for("admin.users"))
