"""Data views and Stats & Charts (descriptive statistics with inline SVG)."""
from flask import Blueprint, render_template, request, g
from .db import q, pivot_values
from .auth import project_access
from .validators import effective_choices, DISPLAY_ONLY, CHOICE_TYPES

bp = Blueprint("reports", __name__)

NUMERIC_TYPES = {"integer", "number", "slider"}


def _entry_fields(pid):
    return [f for f in
            q("SELECT f.*, i.label AS instrument_label FROM fields f"
              " JOIN instruments i ON f.instrument_id=i.id WHERE i.project_id=?"
              " ORDER BY i.position, f.position", (pid,))
            if f["field_type"] not in DISPLAY_ONLY and f["name"] != "record_id"]


@bp.route("/p/<int:pid>/report")
@project_access("read_only")
def report(pid):
    fields = _entry_fields(pid)
    iid = request.args.get("instrument", 0, type=int)
    if iid:
        fields = [f for f in fields if f["instrument_id"] == iid]
    instruments = q("SELECT * FROM instruments WHERE project_id=? ORDER BY position",
                    (pid,))
    events = q("SELECT * FROM events WHERE project_id=? ORDER BY position",
               (pid,)) if g.project["is_longitudinal"] else []
    data, recs = pivot_values(pid)
    rows = []
    if events:
        for rec in recs:
            for e in events:
                vals = [data.get((rec["record_name"], e["id"], f["name"]), "")
                        for f in fields]
                if any(vals):
                    rows.append({"record": rec["record_name"],
                                 "event": e["label"], "vals": vals})
    else:
        rows = [{"record": rec["record_name"], "event": "",
                 "vals": [data.get((rec["record_name"], 0, f["name"]), "")
                            for f in fields]} for rec in recs]
    return render_template("report.html", fields=fields, rows=rows,
                           instruments=instruments, sel_instrument=iid,
                           has_events=bool(events))


@bp.route("/p/<int:pid>/stats")
@project_access("read_only")
def stats(pid):
    fields = _entry_fields(pid)
    values_by_field = {}
    for r in q("SELECT field_name, value FROM data_values WHERE project_id=?"
               " AND value != ''", (pid,)):
        values_by_field.setdefault(r["field_name"], []).append(r["value"])
    n_records = q("SELECT COUNT(*) n FROM records WHERE project_id=?",
                  (pid,), one=True)["n"]
    cards = []
    for f in fields:
        vals = values_by_field.get(f["name"], [])
        card = {"field": f, "n": len(vals), "missing": max(n_records - len(vals), 0)}
        if f["field_type"] in NUMERIC_TYPES or f["validation"] in ("integer", "number"):
            nums = []
            for v in vals:
                try:
                    nums.append(float(v))
                except ValueError:
                    pass
            if nums:
                nums.sort()
                mid = len(nums) // 2
                median = nums[mid] if len(nums) % 2 else (nums[mid - 1] + nums[mid]) / 2
                card["numeric"] = {
                    "min": min(nums), "max": max(nums),
                    "mean": round(sum(nums) / len(nums), 2),
                    "median": round(median, 2)}
        elif f["field_type"] in CHOICE_TYPES or f["field_type"] in ("yesno", "truefalse"):
            counts = {}
            for v in vals:
                parts = v.split(",") if f["field_type"] == "checkbox" else [v]
                for p in parts:
                    p = p.strip()
                    if p:
                        counts[p] = counts.get(p, 0) + 1
            labels = dict(effective_choices(f))
            total = sum(counts.values()) or 1
            card["bars"] = [
                {"label": labels.get(code, code), "count": cnt,
                 "pct": round(100 * cnt / total)}
                for code, cnt in sorted(counts.items(),
                                        key=lambda kv: -kv[1])]
        cards.append(card)
    return render_template("stats.html", cards=cards, n_records=n_records)
