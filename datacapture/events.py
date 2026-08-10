"""Longitudinal events and the event-instrument designation grid."""
from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, g)
from .db import q, x, audit
from .auth import project_access
import re

bp = Blueprint("events", __name__)


@bp.route("/p/<int:pid>/events", methods=["GET", "POST"])
@project_access("admin")
def events(pid):
    if request.method == "POST":
        if g.project["status"] == "production":
            flash("Events are locked in Production.")
            return redirect(url_for("events.events", pid=pid))
        label = request.form.get("label", "").strip()
        if label:
            name = re.sub(r"[^a-z0-9_]+", "_", label.lower()).strip("_")[:50] or "event"
            base, n = name, 1
            while q("SELECT id FROM events WHERE project_id=? AND name=?",
                    (pid, name), one=True):
                n += 1
                name = f"{base}_{n}"
            pos = (q("SELECT COALESCE(MAX(position),0) m FROM events WHERE project_id=?",
                     (pid,), one=True)["m"] or 0) + 1
            x("INSERT INTO events (project_id, name, label, position) VALUES (?,?,?,?)",
              (pid, name, label, pos))
            audit("events.add", pid, details=label)
        return redirect(url_for("events.events", pid=pid))
    evts = q("SELECT * FROM events WHERE project_id=? ORDER BY position", (pid,))
    instruments = q("SELECT * FROM instruments WHERE project_id=? ORDER BY position",
                    (pid,))
    mapping = {(r["event_id"], r["instrument_id"])
               for r in q("SELECT ei.* FROM event_instruments ei"
                          " JOIN events e ON e.id=ei.event_id WHERE e.project_id=?",
                          (pid,))}
    return render_template("events.html", events=evts, instruments=instruments,
                           mapping=mapping)


@bp.route("/p/<int:pid>/events/<int:eid>/<action>", methods=["POST"])
@project_access("admin")
def event_action(pid, eid, action):
    if g.project["status"] == "production":
        flash("Events are locked in Production.")
        return redirect(url_for("events.events", pid=pid))
    evt = q("SELECT * FROM events WHERE id=? AND project_id=?", (eid, pid), one=True)
    if not evt:
        return redirect(url_for("events.events", pid=pid))
    if action == "delete":
        x("DELETE FROM events WHERE id=?", (eid,))
        audit("events.delete", pid, details=evt["label"])
    elif action == "rename":
        label = request.form.get("label", "").strip()
        if label:
            x("UPDATE events SET label=? WHERE id=?", (label, eid))
    elif action in ("up", "down"):
        delta = -1 if action == "up" else 1
        swap = q("SELECT * FROM events WHERE project_id=? AND position=?",
                 (pid, evt["position"] + delta), one=True)
        if swap:
            x("UPDATE events SET position=? WHERE id=?", (evt["position"], swap["id"]))
            x("UPDATE events SET position=? WHERE id=?", (evt["position"] + delta, eid))
    return redirect(url_for("events.events", pid=pid))


@bp.route("/p/<int:pid>/events/map", methods=["POST"])
@project_access("admin")
def map_instruments(pid):
    if g.project["status"] == "production":
        flash("Event designations are locked in Production.")
        return redirect(url_for("events.events", pid=pid))
    event_ids = {r["id"] for r in q("SELECT id FROM events WHERE project_id=?", (pid,))}
    instrument_ids = {r["id"] for r in
                      q("SELECT id FROM instruments WHERE project_id=?", (pid,))}
    x("DELETE FROM event_instruments WHERE event_id IN"
      " (SELECT id FROM events WHERE project_id=?)", (pid,))
    for key in request.form:
        if not key.startswith("map_"):
            continue
        parts = key.split("_")
        if len(parts) != 3:
            continue
        try:
            eid, iid = int(parts[1]), int(parts[2])
        except ValueError:
            continue
        if eid not in event_ids or iid not in instrument_ids:
            continue
        x("INSERT OR IGNORE INTO event_instruments (event_id, instrument_id)"
          " VALUES (?,?)", (eid, iid))
    audit("events.map", pid, details="designation grid updated")
    return redirect(url_for("events.events", pid=pid))
