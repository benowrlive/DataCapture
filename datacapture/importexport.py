"""CSV data import tool (template, validate, review, commit) and exports."""
import csv
import io
import json
import os
import re
import secrets
from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, g, Response, current_app, send_file)
from .db import q, audit, get_db, pivot_values
from .auth import project_access
from .validators import validate_value, DISPLAY_ONLY, effective_choices, FILE_TYPES
from . import files as filestore

bp = Blueprint("importexport", __name__)


def _project_fields(pid):
    return q("SELECT f.*, i.name AS instrument_name, i.id AS iid FROM fields f"
             " JOIN instruments i ON f.instrument_id=i.id WHERE i.project_id=?"
             " ORDER BY i.position, f.position", (pid,))


def _entry_fields(pid):
    return [f for f in _project_fields(pid)
            if f["field_type"] not in DISPLAY_ONLY and f["name"] != "record_id"]


def _importable_fields(pid):
    """Fields that can be set via CSV — excludes file/photo uploads."""
    return [f for f in _entry_fields(pid) if f["field_type"] not in FILE_TYPES]


def _events(pid):
    return q("SELECT * FROM events WHERE project_id=? ORDER BY position", (pid,))


def _tmp_dir():
    d = os.path.join(current_app.config["DATA_DIR"], "tmp_imports")
    os.makedirs(d, exist_ok=True)
    return d


# ------------------------------------------------------------------ import

@bp.route("/p/<int:pid>/import")
@project_access("data_entry")
def import_home(pid):
    return render_template("import.html", stage="upload")


@bp.route("/p/<int:pid>/import/template")
@project_access("data_entry")
def template(pid):
    buf = io.StringIO()
    w = csv.writer(buf)
    header = ["record_id"]
    if g.project["is_longitudinal"]:
        header.append("event_name")
    header += [f["name"] for f in _importable_fields(pid)]
    w.writerow(header)
    if g.project["is_longitudinal"]:
        for e in _events(pid):
            w.writerow(["", e["name"]] + [""] * (len(header) - 2))
    return Response(
        buf.getvalue(), mimetype="text/csv",
        headers={"Content-Disposition":
                 f"attachment; filename=import_template_project{pid}.csv"})


def _parse_upload(pid, file_storage):
    """Returns (rows, errors, warnings). rows = list of dicts with
    record_id, event_id, {field: value} changes; errors = list of dicts."""
    raw = file_storage.read().decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(raw))
    try:
        header = next(reader)
    except StopIteration:
        return None, [{"record": "-", "field": "-", "value": "-",
                       "message": "The file is empty."}], []
    header = [h.strip().lower() for h in header]
    fields_by_name = {f["name"]: f for f in _importable_fields(pid)}
    longitudinal = bool(g.project["is_longitudinal"])
    events_by_name = {e["name"]: e["id"] for e in _events(pid)}

    errors, parsed = [], []
    if not header or header[0] != "record_id":
        errors.append({"record": "-", "field": "-", "value": header[0] if header else "",
                       "message": "First column must be 'record_id'."})
        return None, errors, []
    data_cols = header[1:]
    if longitudinal:
        if len(header) < 2 or header[1] != "event_name":
            errors.append({"record": "-", "field": "-", "value": "",
                           "message": "Longitudinal projects need 'event_name'"
                                      " as the second column."})
            return None, errors, []
        data_cols = header[2:]
    unknown = [c for c in data_cols if c and c not in fields_by_name]
    for c in unknown:
        errors.append({"record": "-", "field": c, "value": "",
                       "message": f"'{c}' is not a variable in this project."
                                  " Do not change template variable names."})
    if errors:
        return None, errors, []

    for lineno, row in enumerate(reader, start=2):
        if not any(c.strip() for c in row):
            continue  # skip empty rows, per Temple guide tip 4
        rec = row[0].strip() if row else ""
        if not rec:
            errors.append({"record": f"line {lineno}", "field": "record_id",
                           "value": "", "message": "Missing record_id."})
            continue
        event_id = 0
        col_offset = 1
        if longitudinal:
            ev = row[1].strip() if len(row) > 1 else ""
            if ev not in events_by_name:
                errors.append({"record": rec, "field": "event_name", "value": ev,
                               "message": f"'{ev}' is not a defined event. Valid: "
                                          + ", ".join(events_by_name)})
                continue
            event_id = events_by_name[ev]
            col_offset = 2
        changes = {}
        for i, col in enumerate(data_cols):
            if not col:
                continue
            v = row[i + col_offset].strip() if len(row) > i + col_offset else ""
            if v == "":
                continue  # blank cells never overwrite, import a few vars at a time
            f = fields_by_name[col]
            err = validate_value(f, v)
            if err:
                errors.append({"record": rec, "field": col, "value": v,
                               "message": err})
            else:
                changes[col] = v
        parsed.append({"record": rec, "event_id": event_id, "changes": changes,
                       "lineno": lineno})
    return parsed, errors, []


@bp.route("/p/<int:pid>/import/upload", methods=["POST"])
@project_access("data_entry")
def upload(pid):
    file = request.files.get("file")
    if not file or not file.filename:
        flash("Please choose a CSV file to upload.")
        return redirect(url_for("importexport.import_home", pid=pid))
    parsed, errors, _ = _parse_upload(pid, file)
    if errors:
        return render_template("import.html", stage="errors", errors=errors)
    # build review table with overwrite detection
    existing = {}
    for r in q("SELECT record_name, event_id, field_name, value FROM data_values"
               " WHERE project_id=?", (pid,)):
        existing[(r["record_name"], r["event_id"], r["field_name"])] = r["value"]
    known_records = {r["record_name"] for r in
                     q("SELECT record_name FROM records WHERE project_id=?", (pid,))}
    review, n_new_records, n_overwrites, n_values = [], 0, 0, 0
    for item in parsed:
        is_new = item["record"] not in known_records
        if is_new:
            n_new_records += 1
            known_records.add(item["record"])
        cells = []
        for fname, v in item["changes"].items():
            old = existing.get((item["record"], item["event_id"], fname))
            overwrite = old is not None and old != v
            if overwrite:
                n_overwrites += 1
            if old != v:
                n_values += 1
            cells.append({"field": fname, "value": v, "old": old,
                          "overwrite": overwrite})
        review.append({"record": item["record"], "event_id": item["event_id"],
                       "is_new": is_new, "cells": cells})
    # stage the parsed data for the confirm step, bound to this project/user
    token = secrets.token_hex(16)
    stage_path = os.path.join(_tmp_dir(), f"{token}.json")
    staged_rows = [
        [item["record"], item["event_id"], fname, v]
        for item in parsed
        for fname, v in item["changes"].items()
    ]
    with open(stage_path, "w", encoding="utf-8") as fh:
        json.dump({"project_id": pid, "user_id": g.user["id"],
                   "rows": staged_rows}, fh)
    events_by_id = {e["id"]: e["label"] for e in _events(pid)}
    return render_template("import.html", stage="review", review=review,
                           token=token, n_new_records=n_new_records,
                           n_overwrites=n_overwrites, n_values=n_values,
                           events_by_id=events_by_id)


@bp.route("/p/<int:pid>/import/commit", methods=["POST"])
@project_access("data_entry")
def commit(pid):
    token = request.form.get("token", "")
    if not token.isalnum():
        flash("Invalid import token.")
        return redirect(url_for("importexport.import_home", pid=pid))
    stage_path = os.path.join(_tmp_dir(), f"{token}.json")
    if not os.path.exists(stage_path):
        flash("Import session expired — please upload the file again.")
        return redirect(url_for("importexport.import_home", pid=pid))
    with open(stage_path, encoding="utf-8") as fh:
        staged = json.load(fh)
    if staged.get("project_id") != pid or staged.get("user_id") != g.user["id"]:
        flash("Import session expired — please upload the file again.")
        return redirect(url_for("importexport.import_home", pid=pid))

    fields_by_name = {f["name"]: f for f in _importable_fields(pid)}
    valid_events = ({e["id"] for e in _events(pid)}
                    if g.project["is_longitudinal"] else {0})
    rows = []
    try:
        for rec, event_id, fname, v in staged.get("rows", []):
            event_id = int(event_id)
            if fname not in fields_by_name or event_id not in valid_events:
                raise ValueError
            err = validate_value(fields_by_name[fname], v)
            if err:
                raise ValueError
            rows.append((str(rec), event_id, str(fname), str(v)))
    except (TypeError, ValueError):
        flash("Import data no longer matches the project design. Please upload again.")
        return redirect(url_for("importexport.import_home", pid=pid))

    db = get_db()
    n = 0
    new_records = set()
    known = {r["record_name"] for r in
             q("SELECT record_name FROM records WHERE project_id=?", (pid,))}
    for rec, event_id, fname, v in rows:
        if rec not in known:
            db.execute("INSERT INTO records (project_id, record_name,"
                       " created_by) VALUES (?,?,?)",
                       (pid, rec, g.user["username"] + " (import)"))
            known.add(rec)
            new_records.add(rec)
        db.execute(
            "INSERT INTO data_values (project_id, record_name, event_id,"
            " field_name, value) VALUES (?,?,?,?,?)"
            " ON CONFLICT(project_id, record_name, event_id, field_name)"
            " DO UPDATE SET value=excluded.value",
            (pid, rec, event_id, fname, v))
        n += 1
    db.commit()
    os.remove(stage_path)
    audit("data.import", pid,
          details=f"{n} values imported, {len(new_records)} new records")
    flash(f"Import complete: {n} values saved, {len(new_records)} new records.")
    return redirect(url_for("records.dashboard", pid=pid))


# ------------------------------------------------------------------ export

@bp.route("/p/<int:pid>/export")
@project_access("read_only")
def export_home(pid):
    instruments = q("SELECT * FROM instruments WHERE project_id=? ORDER BY position",
                    (pid,))
    return render_template("export.html", instruments=instruments)


@bp.route("/p/<int:pid>/export/data.csv")
@project_access("read_only")
def export_data(pid):
    labels = request.args.get("labels") == "1"
    fields = _entry_fields(pid)
    events = _events(pid) if g.project["is_longitudinal"] else []
    events_by_id = {e["id"]: e["name"] for e in events}
    data, recs = pivot_values(pid)

    def fmt(f, v):
        if v == "":
            return v
        if f["field_type"] in FILE_TYPES:
            return filestore.original_name(v)  # export the human filename
        if not labels:
            return v
        ch = dict(effective_choices(f))
        if f["field_type"] == "checkbox":
            return "|".join(ch.get(p.strip(), p.strip()) for p in v.split(","))
        return ch.get(v, v)

    buf = io.StringIO()
    w = csv.writer(buf)
    header = ["record_id"] + (["event_name"] if events else []) \
        + [f["name"] for f in fields]
    w.writerow(header)
    event_ids = [e["id"] for e in events] or [0]
    for rec in recs:
        for eid in event_ids:
            row_vals = [data.get((rec["record_name"], eid, f["name"]), "")
                        for f in fields]
            if events and not any(row_vals):
                continue
            row = [rec["record_name"]]
            if events:
                row.append(events_by_id.get(eid, ""))
            row += [fmt(f, v) for f, v in zip(fields, row_vals)]
            w.writerow(row)
    audit("data.export", pid, details=f"CSV export (labels={labels})")
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition":
                             f"attachment; filename=project{pid}_data.csv"})


@bp.route("/p/<int:pid>/export/dictionary.csv")
@project_access("read_only")
def export_dictionary(pid):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Variable / Field Name", "Form Name", "Field Type", "Field Label",
                "Choices, Calculations, OR Slider Labels", "Field Note",
                "Text Validation Type", "Text Validation Min", "Text Validation Max",
                "Identifier?", "Branching Logic", "Required Field?"])
    for f in _project_fields(pid):
        w.writerow([f["name"], f["instrument_name"], f["field_type"], f["label"],
                    f["choices"], f["field_note"], f["validation"],
                    f["min_value"], f["max_value"], "y" if f["identifier"] else "",
                    f["branching_logic"], "y" if f["required"] else ""])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition":
                             f"attachment; filename=project{pid}_dictionary.csv"})


# ---------------------------------------------------- SPSS .sav (jamovi/R/Stata)

def _sav_frame(pid):
    """Build a pandas DataFrame + SPSS metadata for export.
    Choice fields become labelled numeric variables where their codes are
    integers, else labelled strings. Continuous fields are numeric (scale)."""
    import pandas as pd
    from .validators import CHOICE_TYPES
    fields = [f for f in _entry_fields(pid) if f["field_type"] not in FILE_TYPES]
    events = _events(pid) if g.project["is_longitudinal"] else []
    events_by_id = {e["id"]: e["name"] for e in events}
    data, recs = pivot_values(pid)
    event_ids = [e["id"] for e in events] or [0]

    colnames = ["record_id"] + (["event_name"] if events else []) \
        + [f["name"] for f in fields]
    rows = []
    for rec in recs:
        for eid in event_ids:
            if events and not any((rec["record_name"], eid, f["name"]) in data
                                  for f in fields):
                continue
            row = {"record_id": rec["record_name"]}
            if events:
                row["event_name"] = events_by_id.get(eid, "")
            for f in fields:
                row[f["name"]] = data.get((rec["record_name"], eid, f["name"]), "")
            rows.append(row)
    df = pd.DataFrame(rows, columns=colnames)

    var_labels = {"record_id": "Record ID"}
    if events:
        var_labels["event_name"] = "Event"
    value_labels, measure = {}, {}

    def _codes(v):
        if v in (None, ""):
            return []
        return [s.strip() for s in str(v).split(",") if s.strip()]

    for f in fields:
        name, ft = f["name"], f["field_type"]
        is_num = ft in ("integer", "number", "slider") or \
            f["validation"] in ("integer", "number")
        if ft == "checkbox":
            # expand into one 0/1 variable per option (REDCap-style var___code)
            # so each choice keeps its label in SPSS / jamovi
            for code, lab in effective_choices(f):
                cname = f"{name}___{re.sub(r'[^A-Za-z0-9]+', '_', str(code))}"
                df[cname] = df[name].apply(
                    lambda v, c=code: 1.0 if c in _codes(v) else 0.0)
                var_labels[cname] = f"{f['label']}: {lab}"
                value_labels[cname] = {0.0: "Unchecked", 1.0: "Checked"}
                measure[cname] = "nominal"
            df = df.drop(columns=[name])
            continue
        var_labels[name] = f["label"]
        if is_num:
            df[name] = pd.to_numeric(df[name].replace("", None), errors="coerce")
            measure[name] = "scale"
        elif ft in CHOICE_TYPES or ft in ("yesno", "truefalse"):
            ch = effective_choices(f)
            codes = [c for c, _ in ch]
            if codes and all(str(c).lstrip("-").isdigit() for c in codes):
                df[name] = df[name].apply(
                    lambda v: float(v) if str(v).lstrip("-").isdigit() else None)
                value_labels[name] = {float(c): lab for c, lab in ch}
            else:
                lm = dict(ch)
                df[name] = df[name].apply(lambda v: lm.get(v, v) if v else None)
            measure[name] = "nominal"
        else:  # text, notes, date, etc.
            df[name] = df[name].apply(lambda v: v if v not in (None, "") else None)
            measure[name] = "nominal"
    return df, var_labels, value_labels, measure


@bp.route("/p/<int:pid>/export/data.sav")
@project_access("read_only")
def export_sav(pid):
    try:
        import pyreadstat
    except ImportError:
        flash("The .sav export needs the statistics libraries, which install on "
              "the next full restart of DataCapture. Meanwhile, use the CSV export "
              "— jamovi and SPSS open CSV too.")
        return redirect(url_for("importexport.export_home", pid=pid))
    tmpdir = _tmp_dir()
    # sweep any .sav left behind by an earlier interrupted export (Windows can
    # hold the handle open, so we never rely on post-response deletion for PHI)
    for fn in os.listdir(tmpdir):
        if fn.endswith(".sav"):
            try:
                os.remove(os.path.join(tmpdir, fn))
            except OSError:
                pass
    df, var_labels, value_labels, measure = _sav_frame(pid)
    path = os.path.join(tmpdir, f"{secrets.token_hex(8)}.sav")
    # Carry the project's clinical context into the file so it shows in jamovi/SPSS.
    try:
        spec = g.project["specialty"] or ""
    except (KeyError, IndexError):
        spec = ""
    file_label = (f"{g.project['title']} — {spec}" if spec
                  else g.project["title"])[:64]
    pyreadstat.write_sav(df, path, column_labels=var_labels,
                         variable_value_labels=value_labels,
                         variable_measure=measure, file_label=file_label)
    with open(path, "rb") as fh:
        payload = fh.read()
    try:
        os.remove(path)  # delete before sending — nothing lingers on disk
    except OSError:
        pass
    audit("data.export", pid, details="SPSS .sav export (jamovi/SPSS/R/Stata)")
    return send_file(io.BytesIO(payload), as_attachment=True,
                     download_name=f"project{pid}.sav",
                     mimetype="application/x-spss-sav")
