"""Online Designer: instruments and fields (the data dictionary)."""
import re
import secrets
from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, g, abort)
from .db import q, x, audit
from .auth import project_access
from .validators import FIELD_TYPES, CHOICE_TYPES, VARNAME_RE, parse_choices

bp = Blueprint("designer", __name__)


def _require_dev():
    if g.project["status"] == "production":
        flash("Design is locked: project is in Production. "
              "A global administrator can revert it to Development.")
        return False
    return True


def _slug(text, fallback):
    s = re.sub(r"[^a-z0-9_]+", "_", text.strip().lower()).strip("_")[:50]
    return s if s and VARNAME_RE.match(s) else fallback


@bp.route("/p/<int:pid>/designer")
@project_access("read_only")
def designer(pid):
    instruments = q(
        "SELECT i.*, (SELECT COUNT(*) FROM fields f WHERE f.instrument_id=i.id) n_fields"
        " FROM instruments i WHERE i.project_id=? ORDER BY i.position", (pid,))
    return render_template("designer.html", instruments=instruments)


@bp.route("/p/<int:pid>/designer/instrument", methods=["POST"])
@project_access("admin")
def instrument_add(pid):
    if not _require_dev():
        return redirect(url_for("designer.designer", pid=pid))
    label = request.form.get("label", "").strip() or "New Instrument"
    base = _slug(label, "instrument")
    name, n = base, 1
    while q("SELECT id FROM instruments WHERE project_id=? AND name=?",
            (pid, name), one=True):
        n += 1
        name = f"{base}_{n}"
    pos = (q("SELECT COALESCE(MAX(position),0) m FROM instruments WHERE project_id=?",
             (pid,), one=True)["m"] or 0) + 1
    iid = x("INSERT INTO instruments (project_id, name, label, position)"
            " VALUES (?,?,?,?)", (pid, name, label, pos))
    audit("designer.instrument_add", pid, details=label)
    return redirect(url_for("designer.fields", pid=pid, iid=iid))


@bp.route("/p/<int:pid>/designer/<int:iid>/update", methods=["POST"])
@project_access("admin")
def instrument_update(pid, iid):
    inst = q("SELECT * FROM instruments WHERE id=? AND project_id=?",
             (iid, pid), one=True)
    if not inst:
        abort(404)
    action = request.form.get("action")
    if action == "rename":
        if not _require_dev():
            return redirect(url_for("designer.designer", pid=pid))
        label = request.form.get("label", "").strip()
        if label:
            x("UPDATE instruments SET label=? WHERE id=?", (label, iid))
            audit("designer.instrument_rename", pid, details=f"{inst['label']} -> {label}")
    elif action in ("up", "down"):
        if not _require_dev():
            return redirect(url_for("designer.designer", pid=pid))
        delta = -1 if action == "up" else 1
        swap = q("SELECT * FROM instruments WHERE project_id=? AND position=?",
                 (pid, inst["position"] + delta), one=True)
        if swap:
            x("UPDATE instruments SET position=? WHERE id=?", (inst["position"], swap["id"]))
            x("UPDATE instruments SET position=? WHERE id=?", (inst["position"] + delta, iid))
    elif action == "delete":
        if not _require_dev():
            return redirect(url_for("designer.designer", pid=pid))
        x("DELETE FROM instruments WHERE id=?", (iid,))
        audit("designer.instrument_delete", pid, details=inst["label"])
    elif action == "survey_enable":
        token = inst["survey_token"] or secrets.token_urlsafe(24)
        x("UPDATE instruments SET survey_enabled=1, survey_token=?,"
          " survey_title=?, survey_instructions=? WHERE id=?",
          (token, request.form.get("survey_title", "").strip() or inst["label"],
           request.form.get("survey_instructions", "").strip(), iid))
        audit("survey.enable", pid, details=inst["name"])
    elif action == "survey_disable":
        x("UPDATE instruments SET survey_enabled=0 WHERE id=?", (iid,))
        audit("survey.disable", pid, details=inst["name"])
    return redirect(url_for("designer.designer", pid=pid))


# ------------------------------------------------------------------- fields

@bp.route("/p/<int:pid>/designer/<int:iid>")
@project_access("read_only")
def fields(pid, iid):
    inst = q("SELECT * FROM instruments WHERE id=? AND project_id=?",
             (iid, pid), one=True)
    if not inst:
        abort(404)
    flds = q("SELECT * FROM fields WHERE instrument_id=? ORDER BY position", (iid,))
    edit_id = request.args.get("edit", type=int)
    edit_field = q("SELECT * FROM fields WHERE id=? AND instrument_id=?",
                   (edit_id, iid), one=True) if edit_id else None
    return render_template("fields.html", inst=inst, fields=flds,
                           field_types=FIELD_TYPES, edit_field=edit_field,
                           choice_types=CHOICE_TYPES)


@bp.route("/p/<int:pid>/designer/<int:iid>/field", methods=["POST"])
@project_access("admin")
def field_save(pid, iid):
    if not _require_dev():
        return redirect(url_for("designer.fields", pid=pid, iid=iid))
    inst = q("SELECT * FROM instruments WHERE id=? AND project_id=?",
             (iid, pid), one=True)
    if not inst:
        abort(404)
    fid = request.form.get("field_id", type=int)
    name = request.form.get("name", "").strip().lower()
    label = request.form.get("label", "").strip()
    ftype = request.form.get("field_type", "text")
    if ftype not in {t for t, _ in FIELD_TYPES}:
        flash("Invalid field type.")
        return redirect(url_for("designer.fields", pid=pid, iid=iid))
    if not label:
        flash("Field label is required.")
        return redirect(url_for("designer.fields", pid=pid, iid=iid))
    if not name:
        name = _slug(label, f"field_{secrets.token_hex(3)}")
    if not VARNAME_RE.match(name):
        flash("Variable name must start with a letter and use only "
              "lowercase letters, numbers, underscores (max 50 chars).")
        return redirect(url_for("designer.fields", pid=pid, iid=iid))
    dupe = q("SELECT f.id FROM fields f JOIN instruments i ON f.instrument_id=i.id"
             " WHERE i.project_id=? AND f.name=? AND f.id IS NOT ?",
             (pid, name, fid), one=True)
    if dupe:
        flash(f"Variable name '{name}' is already used in this project.")
        return redirect(url_for("designer.fields", pid=pid, iid=iid))
    if ftype in CHOICE_TYPES and not parse_choices(request.form.get("choices", "")):
        flash("Choice fields need at least one choice, e.g.  1, Yes | 2, No")
        return redirect(url_for("designer.fields", pid=pid, iid=iid))
    vals = (name, label, ftype,
            request.form.get("choices", "").strip(),
            request.form.get("validation", "").strip(),
            request.form.get("min_value", "").strip(),
            request.form.get("max_value", "").strip(),
            1 if request.form.get("required") else 0,
            1 if request.form.get("identifier") else 0,
            request.form.get("branching_logic", "").strip(),
            request.form.get("field_note", "").strip())
    if fid:
        x("UPDATE fields SET name=?, label=?, field_type=?, choices=?, validation=?,"
          " min_value=?, max_value=?, required=?, identifier=?, branching_logic=?,"
          " field_note=? WHERE id=? AND instrument_id=?", vals + (fid, iid))
        audit("designer.field_update", pid, details=f"{inst['name']}.{name}")
    else:
        pos = (q("SELECT COALESCE(MAX(position),0) m FROM fields WHERE instrument_id=?",
                 (iid,), one=True)["m"] or 0) + 1
        x("INSERT INTO fields (instrument_id, name, label, field_type, choices,"
          " validation, min_value, max_value, required, identifier,"
          " branching_logic, field_note, position)"
          " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (iid,) + vals + (pos,))
        audit("designer.field_add", pid, details=f"{inst['name']}.{name}")
    return redirect(url_for("designer.fields", pid=pid, iid=iid))


@bp.route("/p/<int:pid>/designer/<int:iid>/field/<int:fid>/<action>", methods=["POST"])
@project_access("admin")
def field_action(pid, iid, fid, action):
    if not _require_dev():
        return redirect(url_for("designer.fields", pid=pid, iid=iid))
    fld = q("SELECT f.* FROM fields f JOIN instruments i ON f.instrument_id=i.id"
            " WHERE f.id=? AND f.instrument_id=? AND i.project_id=?",
            (fid, iid, pid), one=True)
    if not fld:
        abort(404)
    if action == "delete":
        x("DELETE FROM fields WHERE id=?", (fid,))
        audit("designer.field_delete", pid, details=fld["name"])
    elif action in ("up", "down"):
        delta = -1 if action == "up" else 1
        swap = q("SELECT * FROM fields WHERE instrument_id=? AND position=?",
                 (iid, fld["position"] + delta), one=True)
        if swap:
            x("UPDATE fields SET position=? WHERE id=?", (fld["position"], swap["id"]))
            x("UPDATE fields SET position=? WHERE id=?", (fld["position"] + delta, fid))
    return redirect(url_for("designer.fields", pid=pid, iid=iid))


# ------------------------------------------------------------------ codebook

@bp.route("/p/<int:pid>/codebook")
@project_access("read_only")
def codebook(pid):
    rows = q("SELECT i.label AS instrument_label, i.name AS instrument_name, f.*"
             " FROM fields f JOIN instruments i ON f.instrument_id=i.id"
             " WHERE i.project_id=? ORDER BY i.position, f.position", (pid,))
    return render_template("codebook.html", rows=rows, parse_choices=parse_choices)
