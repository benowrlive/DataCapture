"""Record dashboard, add/edit records, data entry forms."""
from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, g, abort, send_from_directory)
from .db import q, x, audit, get_db
from .auth import project_access
from .validators import (validate_value, branching_visibility, effective_choices,
                         DISPLAY_ONLY, FILE_TYPES)
from . import files as filestore

bp = Blueprint("records", __name__)

STATUS_CYCLE = ("incomplete", "unverified", "complete")


# ---------------------------------------------------------------- helpers

def project_events(pid):
    if not g.project["is_longitudinal"]:
        return []
    return q("SELECT * FROM events WHERE project_id=? ORDER BY position", (pid,))


def instruments_for_event(pid, event_id):
    if not g.project["is_longitudinal"] or not event_id:
        return q("SELECT * FROM instruments WHERE project_id=? ORDER BY position",
                 (pid,))
    return q("SELECT i.* FROM instruments i JOIN event_instruments ei"
             " ON ei.instrument_id=i.id WHERE ei.event_id=? AND i.project_id=?"
             " ORDER BY i.position", (event_id, pid))


def record_values(pid, record_name, event_id):
    return {r["field_name"]: r["value"] for r in
            q("SELECT field_name, value FROM data_values WHERE project_id=?"
              " AND record_name=? AND event_id=?", (pid, record_name, event_id))}


def next_record_name(pid):
    names = [r["record_name"] for r in
             q("SELECT record_name FROM records WHERE project_id=?", (pid,))]
    nums = [int(n) for n in names if n.isdigit()]
    return str(max(nums) + 1 if nums else 1)


def save_form_data(pid, record_name, event_id, inst, fields, form, files=None,
                   username=None):
    """Validate + persist one instrument's submission.
    Returns list of (field, error) tuples; empty list = saved OK."""
    files = files or {}
    values = {}
    current = record_values(pid, record_name, event_id)
    all_values = dict(current)
    file_field_names = {f["name"] for f in fields
                        if f["field_type"] in FILE_TYPES}
    file_errors = {}
    for f in fields:
        if f["field_type"] in DISPLAY_ONLY or f["name"] == "record_id":
            continue
        if f["field_type"] in FILE_TYPES:
            key = "f_" + f["name"]
            old = current.get(f["name"], "")
            storage = files.get(key)
            if storage is not None and getattr(storage, "filename", ""):
                stored, err = filestore.save_upload(
                    pid, record_name, event_id, f["name"], storage)
                if err:
                    file_errors[f["name"]] = err
                    values[f["name"]] = old
                else:
                    if old and old != stored:
                        filestore.delete_stored(pid, record_name, event_id, old)
                    values[f["name"]] = stored
            elif form.get(key + "__remove"):
                if old:
                    filestore.delete_stored(pid, record_name, event_id, old)
                values[f["name"]] = ""
            else:
                values[f["name"]] = old  # unchanged
        elif f["field_type"] == "checkbox":
            vals = form.getlist("f_" + f["name"])
            values[f["name"]] = ",".join(v.strip() for v in vals if v.strip())
        else:
            values[f["name"]] = (form.get("f_" + f["name"]) or "").strip()
        all_values[f["name"]] = values[f["name"]]
    visible = branching_visibility(fields, all_values)

    errors = []
    for f in fields:
        if f["name"] not in values or not visible.get(f["name"], True):
            continue
        if f["name"] in file_errors:
            errors.append((f, file_errors[f["name"]]))
            continue
        err = validate_value(f, values[f["name"]])
        if err:
            errors.append((f, err))
    if errors:
        return errors

    db = get_db()
    changed = []
    for name, v in values.items():
        old = current.get(name)
        if not visible.get(name, True):
            if old is not None:
                if name in file_field_names:
                    filestore.delete_stored(pid, record_name, event_id, old)
                db.execute(
                    "DELETE FROM data_values WHERE project_id=? AND record_name=?"
                    " AND event_id=? AND field_name=?",
                    (pid, record_name, event_id, name))
                changed.append(f"{name}: {old!r} -> '' (hidden)")
            continue
        if old == v or (old is None and v == ""):
            continue
        if v == "" and name in file_field_names:
            db.execute(
                "DELETE FROM data_values WHERE project_id=? AND record_name=?"
                " AND event_id=? AND field_name=?",
                (pid, record_name, event_id, name))
            changed.append(f"{name}: {old!r} -> '' (removed)")
            continue
        db.execute(
            "INSERT INTO data_values (project_id, record_name, event_id,"
            " field_name, value) VALUES (?,?,?,?,?)"
            " ON CONFLICT(project_id, record_name, event_id, field_name)"
            " DO UPDATE SET value=excluded.value",
            (pid, record_name, event_id, name, v))
        changed.append(f"{name}: {old!r} -> {v!r}")
    status = form.get("form_status", "incomplete")
    if status not in STATUS_CYCLE:
        status = "incomplete"
    db.execute(
        "INSERT INTO form_status (project_id, record_name, event_id,"
        " instrument_id, status) VALUES (?,?,?,?,?)"
        " ON CONFLICT(project_id, record_name, event_id, instrument_id)"
        " DO UPDATE SET status=excluded.status",
        (pid, record_name, event_id, inst["id"], status))
    db.commit()
    if changed:
        audit("data.save", pid, record_name,
              f"[{inst['name']}] " + "; ".join(changed), username=username)
    return []


# ------------------------------------------------------------------ routes

@bp.route("/p/<int:pid>/records")
@project_access("read_only")
def dashboard(pid):
    recs = q("SELECT * FROM records WHERE project_id=?"
             " ORDER BY CAST(record_name AS INTEGER), record_name", (pid,))
    events = project_events(pid)
    instruments = q("SELECT * FROM instruments WHERE project_id=? ORDER BY position",
                    (pid,))
    mapping = None
    if events:
        mapping = {(r["event_id"], r["instrument_id"]) for r in
                   q("SELECT ei.* FROM event_instruments ei JOIN events e"
                     " ON e.id=ei.event_id WHERE e.project_id=?", (pid,))}
    statuses = {(r["record_name"], r["event_id"], r["instrument_id"]): r["status"]
                for r in q("SELECT * FROM form_status WHERE project_id=?", (pid,))}
    return render_template("records.html", records=recs, events=events,
                           instruments=instruments, statuses=statuses,
                           mapping=mapping)


@bp.route("/p/<int:pid>/records/new", methods=["POST"])
@project_access("data_entry")
def add_record(pid):
    name = (request.form.get("record_name") or "").strip() or next_record_name(pid)
    if q("SELECT id FROM records WHERE project_id=? AND record_name=?",
         (pid, name), one=True):
        flash(f"Record '{name}' already exists.")
        return redirect(url_for("records.dashboard", pid=pid))
    x("INSERT INTO records (project_id, record_name, created_by) VALUES (?,?,?)",
      (pid, name, g.user["username"]))
    audit("record.create", pid, name)
    return redirect(url_for("records.dashboard", pid=pid))


@bp.route("/p/<int:pid>/records/<record_name>/delete", methods=["POST"])
@project_access("admin")
def delete_record(pid, record_name):
    x("DELETE FROM data_values WHERE project_id=? AND record_name=?",
      (pid, record_name))
    x("DELETE FROM form_status WHERE project_id=? AND record_name=?",
      (pid, record_name))
    x("DELETE FROM records WHERE project_id=? AND record_name=?",
      (pid, record_name))
    filestore.delete_record_files(pid, record_name)
    audit("record.delete", pid, record_name)
    flash(f"Record '{record_name}' deleted.")
    return redirect(url_for("records.dashboard", pid=pid))


@bp.route("/p/<int:pid>/entry/<record_name>/<int:iid>", methods=["GET", "POST"])
@project_access("read_only")
def entry(pid, record_name, iid):
    rec = q("SELECT * FROM records WHERE project_id=? AND record_name=?",
            (pid, record_name), one=True)
    inst = q("SELECT * FROM instruments WHERE id=? AND project_id=?",
             (iid, pid), one=True)
    if not rec or not inst:
        abort(404)
    event_id = request.args.get("event", 0, type=int)
    event = None
    if g.project["is_longitudinal"]:
        event = q("SELECT * FROM events WHERE id=? AND project_id=?",
                  (event_id, pid), one=True)
        if not event:
            abort(404)
        mapped = q("SELECT 1 FROM event_instruments WHERE event_id=?"
                   " AND instrument_id=?", (event_id, iid), one=True)
        if not mapped:
            abort(404)
    else:
        event_id = 0
    fields = q("SELECT * FROM fields WHERE instrument_id=? ORDER BY position", (iid,))
    errors = []
    if request.method == "POST":
        if g.role == "read_only":
            abort(403)
        errors = save_form_data(pid, record_name, event_id, inst, fields,
                                request.form, request.files)
        if not errors:
            flash("Form saved.")
            return redirect(url_for("records.dashboard", pid=pid))
    values = record_values(pid, record_name, event_id)
    if request.method == "POST":  # re-show submitted values on error
        for f in fields:
            if f["field_type"] in FILE_TYPES:
                continue  # keep the stored value; uploads aren't re-shown
            if f["field_type"] == "checkbox":
                values[f["name"]] = ",".join(request.form.getlist("f_" + f["name"]))
            elif "f_" + f["name"] in request.form:
                values[f["name"]] = request.form.get("f_" + f["name"])
    status_row = q("SELECT status FROM form_status WHERE project_id=? AND"
                   " record_name=? AND event_id=? AND instrument_id=?",
                   (pid, record_name, event_id, iid), one=True)
    return render_template(
        "entry.html", rec=rec, inst=inst, event=event, fields=fields,
        values=values, errors={f["name"]: e for f, e in errors},
        status=(status_row["status"] if status_row else "incomplete"),
        effective_choices=effective_choices, readonly=(g.role == "read_only"),
        file_ctx={"pid": pid, "record": record_name, "event": event_id},
        original_name=filestore.original_name,
        branching_json={f["name"]: f["branching_logic"]
                        for f in fields if f["branching_logic"]})


@bp.route("/p/<int:pid>/file/<record_name>/<field_name>")
@project_access("read_only")
def download_file(pid, record_name, field_name):
    event_id = request.args.get("event", 0, type=int)
    row = q("SELECT value FROM data_values WHERE project_id=? AND record_name=?"
            " AND event_id=? AND field_name=?",
            (pid, record_name, event_id, field_name), one=True)
    if not row or not row["value"]:
        abort(404)
    directory = filestore.event_dir(pid, record_name, event_id)
    resp = send_from_directory(directory, row["value"], as_attachment=False,
                               download_name=filestore.original_name(row["value"]))
    # never let the browser guess a different content type than the extension
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp
