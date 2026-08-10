"""Project list, creation, setup page, production mode, user rights."""
from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, g, abort)
from .db import q, x, audit, get_db
from .auth import login_required, project_access, ROLES
from . import files as filestore

bp = Blueprint("projects", __name__)

PURPOSES = ["research", "quality_improvement", "operational_support",
            "practice"]


@bp.route("/projects")
@login_required
def home():
    user = g.user
    if user["is_admin"]:
        projects = q("SELECT p.*, 'admin' AS role FROM projects p ORDER BY p.id DESC")
    else:
        projects = q(
            "SELECT p.*, pu.role FROM projects p"
            " JOIN project_users pu ON pu.project_id = p.id"
            " WHERE pu.user_id=? ORDER BY p.id DESC", (user["id"],))
    counts = {r["project_id"]: r["n"] for r in
              q("SELECT project_id, COUNT(*) n FROM records GROUP BY project_id")}
    return render_template("projects.html", projects=projects, counts=counts)


@bp.route("/projects/new", methods=["GET", "POST"])
@login_required
def new():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        if not title:
            flash("Project title is required.")
            return redirect(url_for("projects.new"))

        is_longitudinal = bool(request.form.get("is_longitudinal"))
        record_label = (request.form.get("record_label", "Record ID").strip()
                        or "Record ID")
        pid = x("INSERT INTO projects (title, purpose, specialty, notes,"
                " is_longitudinal, record_label, created_by) VALUES (?,?,?,?,?,?,?)",
                (title, request.form.get("purpose", "research"),
                 request.form.get("specialty", "").strip(),
                 request.form.get("notes", "").strip(),
                 1 if is_longitudinal else 0, record_label, g.user["id"]))
        x("INSERT INTO project_users (project_id, user_id, role) VALUES (?,?,'admin')",
          (pid, g.user["id"]))
        # every project starts with one instrument holding the key field
        iid = x("INSERT INTO instruments (project_id, name, label, position)"
                " VALUES (?,?,?,1)", (pid, "form_1", "Form 1"))
        x("INSERT INTO fields (instrument_id, name, label, field_type, position)"
          " VALUES (?,?,?,?,1)", (iid, "record_id", "Record ID", "text"))
        if is_longitudinal:
            eid = x("INSERT INTO events (project_id, name, label, position)"
                    " VALUES (?,?,?,1)", (pid, "baseline", "Baseline"))
            x("INSERT INTO event_instruments (event_id, instrument_id)"
              " VALUES (?,?)", (eid, iid))
        audit("project.create", pid, details=title)
        return redirect(url_for("projects.setup", pid=pid))
    return render_template("project_new.html", purposes=PURPOSES)


@bp.route("/p/<int:pid>")
@project_access("read_only")
def setup(pid):
    instruments = q("SELECT * FROM instruments WHERE project_id=? ORDER BY position",
                    (pid,))
    events = q("SELECT * FROM events WHERE project_id=? ORDER BY position", (pid,))
    n_records = q("SELECT COUNT(*) n FROM records WHERE project_id=?",
                  (pid,), one=True)["n"]
    n_fields = q("SELECT COUNT(*) n FROM fields f JOIN instruments i"
                 " ON f.instrument_id=i.id WHERE i.project_id=?", (pid,), one=True)["n"]
    members = q("SELECT u.username, u.display_name, pu.role FROM project_users pu"
                " JOIN users u ON u.id=pu.user_id WHERE pu.project_id=?", (pid,))
    return render_template("project_setup.html", instruments=instruments,
                           events=events, n_records=n_records, n_fields=n_fields,
                           members=members)


@bp.route("/p/<int:pid>/status", methods=["POST"])
@project_access("admin")
def change_status(pid):
    target = request.form.get("target")
    if target == "production" and g.project["status"] == "dev":
        x("UPDATE projects SET status='production' WHERE id=?", (pid,))
        audit("project.production", pid, details="moved to production")
        flash("Project moved to PRODUCTION. Design changes are now locked.")
    elif target == "dev" and g.project["status"] == "production":
        if not g.user["is_admin"]:
            abort(403)  # only global admin can revert, like REDCap
        x("UPDATE projects SET status='dev' WHERE id=?", (pid,))
        audit("project.dev", pid, details="reverted to development")
        flash("Project reverted to Development mode.")
    return redirect(url_for("projects.setup", pid=pid))


@bp.route("/p/<int:pid>/delete", methods=["POST"])
@project_access("admin")
def delete_project(pid):
    """Permanently delete a project and everything in it (admin only)."""
    title = g.project["title"]
    db = get_db()
    db.execute("DELETE FROM data_values WHERE project_id=?", (pid,))
    db.execute("DELETE FROM form_status WHERE project_id=?", (pid,))
    db.execute("DELETE FROM records WHERE project_id=?", (pid,))
    db.execute("DELETE FROM event_instruments WHERE event_id IN"
               " (SELECT id FROM events WHERE project_id=?)", (pid,))
    db.execute("DELETE FROM events WHERE project_id=?", (pid,))
    db.execute("DELETE FROM fields WHERE instrument_id IN"
               " (SELECT id FROM instruments WHERE project_id=?)", (pid,))
    db.execute("DELETE FROM instruments WHERE project_id=?", (pid,))
    db.execute("DELETE FROM project_users WHERE project_id=?", (pid,))
    db.execute("DELETE FROM projects WHERE id=?", (pid,))
    db.commit()
    filestore.delete_project_files(pid)
    audit("project.delete", None,
          details=f"deleted project #{pid} '{title}' and all its data",
          username=g.user["username"])
    flash(f"Project '{title}' and all of its data were permanently deleted.")
    return redirect(url_for("projects.home"))


@bp.route("/p/<int:pid>/settings", methods=["POST"])
@project_access("admin")
def settings(pid):
    if g.project["status"] == "production":
        flash("Settings are locked in Production.")
        return redirect(url_for("projects.setup", pid=pid))
    x("UPDATE projects SET title=?, specialty=?, notes=?, record_label=?,"
      " is_longitudinal=? WHERE id=?",
      (request.form.get("title", g.project["title"]).strip() or g.project["title"],
       request.form.get("specialty", g.project["specialty"] or "").strip(),
       request.form.get("notes", "").strip(),
       request.form.get("record_label", "Record ID").strip() or "Record ID",
       1 if request.form.get("is_longitudinal") else 0, pid))
    audit("project.settings", pid, details="settings updated")
    return redirect(url_for("projects.setup", pid=pid))


# ------------------------------------------------------------- user rights

@bp.route("/p/<int:pid>/users", methods=["GET", "POST"])
@project_access("admin")
def users(pid):
    if request.method == "POST":
        uid = request.form.get("user_id", type=int)
        role = request.form.get("role")
        if role in ROLES and uid:
            target = q("SELECT * FROM users WHERE id=?", (uid,), one=True)
            if target:
                x("INSERT INTO project_users (project_id, user_id, role) VALUES (?,?,?)"
                  " ON CONFLICT(project_id, user_id) DO UPDATE SET role=excluded.role",
                  (pid, uid, role))
                audit("rights.grant", pid,
                      details=f"{target['username']} -> {role}")
        return redirect(url_for("projects.users", pid=pid))
    members = q("SELECT u.id, u.username, u.display_name, pu.role FROM project_users pu"
                " JOIN users u ON u.id=pu.user_id WHERE pu.project_id=?"
                " ORDER BY u.username", (pid,))
    member_ids = [m["id"] for m in members]
    others = [u for u in q("SELECT id, username, display_name FROM users"
                           " WHERE active=1 ORDER BY username")
              if u["id"] not in member_ids]
    return render_template("project_users.html", members=members, others=others,
                           roles=ROLES)


@bp.route("/p/<int:pid>/users/<int:uid>/remove", methods=["POST"])
@project_access("admin")
def remove_user(pid, uid):
    target = q("SELECT username FROM users WHERE id=?", (uid,), one=True)
    x("DELETE FROM project_users WHERE project_id=? AND user_id=?", (pid, uid))
    audit("rights.revoke", pid, details=target["username"] if target else str(uid))
    return redirect(url_for("projects.users", pid=pid))


# ------------------------------------------------------------- audit viewer

@bp.route("/p/<int:pid>/audit")
@project_access("admin")
def audit_view(pid):
    page = max(request.args.get("page", 1, type=int), 1)
    per = 100
    rows = q("SELECT * FROM audit_log WHERE project_id=? ORDER BY id DESC"
             " LIMIT ? OFFSET ?", (pid, per, (page - 1) * per))
    total = q("SELECT COUNT(*) n FROM audit_log WHERE project_id=?",
              (pid,), one=True)["n"]
    return render_template("audit.html", rows=rows, page=page,
                           pages=(total + per - 1) // per)
