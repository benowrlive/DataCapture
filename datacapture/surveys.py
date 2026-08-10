"""Public survey routes — the only unauthenticated pages in the app."""
from flask import Blueprint, render_template, request, abort
from .db import q, audit, get_db
from .validators import (validate_value, branching_visibility, effective_choices,
                         DISPLAY_ONLY, FILE_TYPES)
from . import files as filestore

bp = Blueprint("surveys", __name__)


def _load(token):
    inst = q("SELECT * FROM instruments WHERE survey_token=? AND survey_enabled=1",
             (token,), one=True)
    if not inst:
        abort(404)
    project = q("SELECT * FROM projects WHERE id=?", (inst["project_id"],), one=True)
    fields = q("SELECT * FROM fields WHERE instrument_id=? ORDER BY position",
               (inst["id"],))
    return inst, project, fields


def _survey_event_id(project, inst):
    """First event this instrument is designated for (longitudinal projects)."""
    if not project["is_longitudinal"]:
        return 0
    row = q("SELECT e.id FROM events e JOIN event_instruments ei"
            " ON ei.event_id=e.id WHERE e.project_id=? AND ei.instrument_id=?"
            " ORDER BY e.position LIMIT 1", (project["id"], inst["id"]), one=True)
    return row["id"] if row else 0


@bp.route("/s/<token>", methods=["GET", "POST"])
def survey(token):
    inst, project, fields = _load(token)
    entry_fields = [f for f in fields if f["name"] != "record_id"]
    errors = {}
    values = {}
    if request.method == "POST":
        all_values = {}
        pending_files = {}
        for f in entry_fields:
            if f["field_type"] in DISPLAY_ONLY:
                continue
            if f["field_type"] in FILE_TYPES:
                storage = request.files.get("f_" + f["name"])
                if storage is not None and getattr(storage, "filename", ""):
                    if filestore.allowed(storage.filename):
                        pending_files[f["name"]] = storage
                        all_values[f["name"]] = "1"
                    else:
                        errors[f["name"]] = ("File type not allowed. Use an "
                                             "image, PDF, Word, text, or "
                                             "spreadsheet file.")
                        all_values[f["name"]] = ""
                else:
                    all_values[f["name"]] = ""
                continue
            if f["field_type"] == "checkbox":
                v = ",".join(x_.strip() for x_ in request.form.getlist("f_" + f["name"])
                             if x_.strip())
            else:
                v = (request.form.get("f_" + f["name"]) or "").strip()
            values[f["name"]] = v
            all_values[f["name"]] = v
        visible = branching_visibility(entry_fields, all_values)
        for f in entry_fields:
            if not visible.get(f["name"], True) or f["name"] in errors:
                continue
            if f["field_type"] in FILE_TYPES:
                if f["required"] and f["name"] not in pending_files:
                    errors[f["name"]] = "This field is required."
                continue
            if f["name"] not in values:
                continue
            err = validate_value(f, values[f["name"]])
            if err:
                errors[f["name"]] = err
        if not errors:
            db = get_db()
            # allocate the next record number atomically-ish
            names = [r["record_name"] for r in
                     q("SELECT record_name FROM records WHERE project_id=?",
                       (project["id"],))]
            nums = [int(n) for n in names if n.isdigit()]
            record_name = str(max(nums) + 1 if nums else 1)
            event_id = _survey_event_id(project, inst)
            db.execute("INSERT INTO records (project_id, record_name, created_by)"
                       " VALUES (?,?, 'survey')", (project["id"], record_name))
            for name, v in values.items():
                if not visible.get(name, True):
                    continue
                if v != "":
                    db.execute(
                        "INSERT INTO data_values (project_id, record_name,"
                        " event_id, field_name, value) VALUES (?,?,?,?,?)",
                        (project["id"], record_name, event_id, name, v))
            for name, storage in pending_files.items():
                if not visible.get(name, True):
                    continue
                stored, err = filestore.save_upload(
                    project["id"], record_name, event_id, name, storage)
                if not err and stored:
                    db.execute(
                        "INSERT INTO data_values (project_id, record_name,"
                        " event_id, field_name, value) VALUES (?,?,?,?,?)",
                        (project["id"], record_name, event_id, name, stored))
            db.execute(
                "INSERT INTO form_status (project_id, record_name, event_id,"
                " instrument_id, status) VALUES (?,?,?,?,'complete')",
                (project["id"], record_name, event_id, inst["id"]))
            db.commit()
            audit("survey.response", project["id"], record_name,
                  f"[{inst['name']}] submitted via public link", username="survey")
            return render_template("survey_done.html", inst=inst)
    return render_template(
        "survey.html", inst=inst, project=project, fields=entry_fields,
        values=values, errors=errors, effective_choices=effective_choices,
        branching_json={f["name"]: f["branching_logic"]
                        for f in entry_fields if f["branching_logic"]})
