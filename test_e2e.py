"""End-to-end smoke test using Flask's test client."""
import io
import os
import re
import shutil
import sys
import tempfile

sys.path.insert(0, ".")
from datacapture import create_app  # noqa: E402
from datacapture.db import q as dbq  # noqa: E402
from reset_admin_password import reset_password  # noqa: E402

tmp = tempfile.mkdtemp()
app = create_app(data_dir=tmp)
app.config["TESTING"] = True
c = app.test_client()
FAIL = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra if not cond else "")
    if not cond:
        FAIL.append(name)


# ---- first run + login
r = c.get("/", follow_redirects=True)
check("redirects to setup", b"administrator account" in r.data)
r = c.post("/setup", data={"username": "admin", "password": "password123",
                           "display_name": "Dr Admin"}, follow_redirects=True)
check("admin created -> login page", b"Log in" in r.data)
r = c.post("/login", data={"username": "admin", "password": "wrong"})
check("bad password rejected", b"Invalid" in r.data)
r = c.get("/forgot-password")
check("forgot password page", b"reset_password.bat" in r.data)
r = c.post("/login?next=https://evil.example",
           data={"username": "admin", "password": "password123"})
check("external next ignored", r.status_code == 302 and
      r.headers.get("Location", "").endswith("/projects"))
c.get("/logout")
ok, msg = reset_password("admin", "newpass123", tmp)
check("local password reset works", ok and "admin" in msg)
r = c.post("/login", data={"username": "admin", "password": "password123"})
check("old password rejected after reset", b"Invalid" in r.data)
r = c.post("/login", data={"username": "admin", "password": "newpass123"},
           follow_redirects=True)
check("login ok", b"My Projects" in r.data)

# ---- create longitudinal project
r = c.post("/projects/new", data={"title": "TB Cohort Study", "purpose": "research",
                                  "specialty": "Infectious Diseases",
                                  "notes": "test", "record_label": "Participant ID",
                                  "is_longitudinal": "1"}, follow_redirects=True)
check("project created", b"TB Cohort Study" in r.data)

# ---- specialty context: picker, storage, dashboard display, tailored hints
r = c.get("/projects/new")
check("specialty picker present",
      b"specialty_suggest" in r.data and b"Infectious Diseases" in r.data)
check("non-clinical department excluded", b"Directorate" not in r.data)
r = c.get("/p/1")
check("specialty shown on dashboard", b"Infectious Diseases" in r.data)
r = c.get("/p/1/designer")
check("suggestions tailored to specialty (instrument)",
      b"Antimicrobial Stewardship" in r.data)
r = c.get("/p/1/designer/1")
check("suggestions tailored to specialty (field)", b"Procalcitonin" in r.data)

# ---- designer: rename starter instrument, add fields
r = c.post("/p/1/designer/1/update", data={"action": "rename", "label": "Demographics"},
           follow_redirects=True)
check("instrument renamed", b"Demographics" in r.data)

fields = [
    dict(label="Full name", name="full_name", field_type="text", identifier="1",
         required="1"),
    dict(label="Age", name="age", field_type="integer", min_value="0",
         max_value="120", required="1"),
    dict(label="Sex", name="sex", field_type="radio",
         choices="1, Male | 2, Female", required="1"),
    dict(label="Symptoms", name="symptoms", field_type="checkbox",
         choices="1, Fever | 2, Cough | 3, Weight loss"),
    dict(label="Pregnant?", name="pregnant", field_type="yesno",
         branching_logic="[sex] = '2'"),
    dict(label="Visit date", name="visit_date", field_type="date"),
]
for f in fields:
    r = c.post("/p/1/designer/1/field", data=f, follow_redirects=True)
check("fields added", all(n.encode() in r.data for n in
                          ["full_name", "age", "sex", "symptoms", "pregnant"]))
r = c.post("/p/1/designer/1/field",
           data=dict(label="Bad name", name="1bad", field_type="text"),
           follow_redirects=True)
check("bad varname rejected", b"Variable name must" in r.data)
r = c.post("/p/1/designer/1/field",
           data=dict(label="Dup", name="age", field_type="text"),
           follow_redirects=True)
check("duplicate varname rejected", b"already used" in r.data)
r = c.post("/p/1/designer/1/field",
           data=dict(label="Bad type", name="bad_type", field_type="bogus"),
           follow_redirects=True)
check("invalid field type rejected", b"Invalid field type" in r.data)

# second instrument
r = c.post("/p/1/designer/instrument", data={"label": "Lab Results"},
           follow_redirects=True)
r = c.post("/p/1/designer/2/field",
           data=dict(label="CRP (mg/L)", name="crp", field_type="number"),
           follow_redirects=True)
check("second instrument + field", b"crp" in r.data)

# ---- events
r = c.post("/p/1/events", data={"label": "Week 4"}, follow_redirects=True)
check("event added", b"Week 4" in r.data)
# map: baseline(1) gets both, week4(2) gets labs only
r = c.post("/p/1/events/map",
           data={"map_1_1": "1", "map_1_2": "1", "map_2_2": "1"},
           follow_redirects=True)
check("event mapping saved", r.status_code == 200)

# ---- records + data entry
r = c.post("/p/1/records/new", data={"record_name": ""}, follow_redirects=True)
check("record auto-numbered", b">1<" in r.data or b"<strong>1</strong>" in r.data)
# entry with a validation error (age too high)
r = c.post("/p/1/entry/1/1?event=1",
           data={"f_full_name": "Jane Doe", "f_age": "300", "f_sex": "2",
                 "f_symptoms": ["1", "3"], "f_pregnant": "0",
                 "f_visit_date": "2026-07-01", "form_status": "complete"})
check("range validation blocks save", "must be ≤ 120".encode() in r.data)
r = c.post("/p/1/entry/1/1?event=1",
           data={"f_full_name": "Jane Doe", "f_age": "34", "f_sex": "2",
                 "f_symptoms": ["1", "3"], "f_pregnant": "0",
                 "f_visit_date": "2026-07-01", "form_status": "complete"},
           follow_redirects=True)
check("valid entry saved", b"Form saved" in r.data)
# branching: male record should not require 'pregnant'
r = c.post("/p/1/records/new", data={"record_name": "2"}, follow_redirects=True)
r = c.post("/p/1/entry/2/1?event=1",
           data={"f_full_name": "John Roe", "f_age": "40", "f_sex": "1",
                 "f_visit_date": "2026-07-02", "form_status": "unverified"},
           follow_redirects=True)
check("branching-hidden field not required", b"Form saved" in r.data)
r = c.post("/p/1/entry/2/1?event=1",
           data={"f_full_name": "John Roe", "f_age": "40", "f_sex": "1",
                 "f_pregnant": "1", "f_visit_date": "2026-07-02",
                 "form_status": "unverified"}, follow_redirects=True)
check("branching-hidden submitted value ignored", b"Form saved" in r.data)
with app.app_context():
    hidden = dbq("SELECT value FROM data_values WHERE project_id=1"
                 " AND record_name='2' AND event_id=1 AND field_name='pregnant'",
                 one=True)
check("branching-hidden value not stored", hidden is None)
r = c.post("/p/1/entry/1/1?event=2", data={"f_age": "55"})
check("unmapped event-instrument rejected", r.status_code == 404)

# ---- survey
r = c.post("/p/1/designer/2/update",
           data={"action": "survey_enable", "survey_title": "Lab self-report",
                 "survey_instructions": "Please fill"}, follow_redirects=True)
m = re.search(rb"/s/([A-Za-z0-9_\-]+)", r.data)
check("survey token generated", bool(m))
token = m.group(1).decode()
r = c.get(f"/s/{token}")
check("public survey loads without login", b"Lab self-report" in r.data)
r = c.post(f"/s/{token}", data={"f_crp": "abc"})
check("survey validation", b"must be a number" in r.data)
r = c.post(f"/s/{token}", data={"f_crp": "12.5"})
check("survey submits", b"Thank you" in r.data)

# ---- import
r = c.get("/p/1/import/template")
check("template downloads", r.data.startswith(b"record_id,event_name"))
csv_data = ("record_id,event_name,age,sex,crp\n"
            "1,baseline,35,2,\n"          # overwrite age 34 -> 35
            "10,baseline,50,1,\n"          # new record
            "10,week_4,,,7.7\n")
r = c.post("/p/1/import/upload",
           data={"file": (io.BytesIO(csv_data.encode()), "import.csv")},
           content_type="multipart/form-data")
check("import review shows overwrite", b"overwrite" in r.data and b"35" in r.data)
m = re.search(rb'name="token" value="([a-f0-9]+)"', r.data)
check("import token present", bool(m))
token = m.group(1).decode()
r = c.post("/projects/new", data={"title": "Other Project",
                                  "purpose": "research",
                                  "record_label": "Record ID"},
           follow_redirects=True)
check("second project created", b"Other Project" in r.data)
r = c.post("/p/2/import/commit", data={"token": token}, follow_redirects=True)
check("import token cannot cross projects",
      b"Import session expired" in r.data and b"Import complete" not in r.data)
r = c.post("/p/1/import/commit", data={"token": token},
           follow_redirects=True)
check("import commits", b"Import complete" in r.data)
bad_csv = "record_id,event_name,sex\n5,baseline,9\n"
r = c.post("/p/1/import/upload",
           data={"file": (io.BytesIO(bad_csv.encode()), "bad.csv")},
           content_type="multipart/form-data")
check("import invalid category error",
      b"not a valid category" in r.data and b"Errors were detected" in r.data)

# ---- export / reports / stats / codebook / audit
r = c.get("/p/1/export/data.csv")
check("export raw", b"record_id,event_name" in r.data and b"35" in r.data
      and b"7.7" in r.data)
r = c.get("/p/1/export/data.csv?labels=1")
check("export labels", b"Female" in r.data)
r = c.get("/p/1/export/dictionary.csv")
check("dictionary export", b"Variable / Field Name" in r.data)
r = c.get("/p/1/report")
check("report table", b"Jane Doe" in r.data)
r = c.get("/p/1/stats")
check("stats page", b"Stats" in r.data and b"Female" in r.data)
r = c.get("/p/1/codebook")
check("codebook", b"crp" in r.data)
r = c.get("/p/1/audit")
check("audit trail records changes", b"data.save" in r.data or b"data.import" in r.data)

# ---- users & rights
r = c.post("/admin/users", data={"username": "nurse1", "password": "password456",
                                 "display_name": "Nurse One"}, follow_redirects=True)
check("second user created", b"nurse1" in r.data)
r = c.post("/p/1/users", data={"user_id": "2", "role": "read_only"},
           follow_redirects=True)
check("granted read_only", b"Read Only" in r.data)
c.get("/logout")
r = c.post("/login", data={"username": "nurse1", "password": "password456"},
           follow_redirects=True)
check("nurse login", b"TB Cohort" in r.data)
r = c.post("/p/1/entry/1/1?event=1", data={"f_age": "99"})
check("read_only cannot save", r.status_code == 403)
r = c.post("/p/1/records/new", data={"record_name": "99"})
check("read_only cannot add record", r.status_code == 403)
r = c.get("/p/1/audit")
check("read_only cannot view audit", r.status_code == 403)

# ---- re-authenticate as admin for the remaining project-building tests
c.get("/logout")
c.post("/login", data={"username": "admin", "password": "newpass123"})

# ---- file / photo attachment field (classic project)
r = c.post("/projects/new", data={"title": "Imaging Project", "purpose": "research",
                                  "record_label": "Case ID"}, follow_redirects=True)
with app.app_context():
    img_pid = dbq("SELECT id FROM projects WHERE title='Imaging Project'",
                  one=True)["id"]
    img_iid = dbq("SELECT id FROM instruments WHERE project_id=? ORDER BY position"
                  " LIMIT 1", (img_pid,), one=True)["id"]
r = c.post(f"/p/{img_pid}/designer/{img_iid}/field",
           data=dict(label="Scan upload", name="scan", field_type="file",
                     required="1"), follow_redirects=True)
check("file field added", b"scan" in r.data and b"file" in r.data)
r = c.post(f"/p/{img_pid}/records/new", data={"record_name": "A1"},
           follow_redirects=True)
# required file missing -> blocked
r = c.post(f"/p/{img_pid}/entry/A1/{img_iid}",
           data={"form_status": "complete"})
check("required file enforced", b"required" in r.data.lower())
# upload a PNG
png = (b"\x89PNG\r\n\x1a\n" + b"0" * 64)
r = c.post(f"/p/{img_pid}/entry/A1/{img_iid}",
           data={"form_status": "complete", "f_scan": (io.BytesIO(png), "xray.png")},
           content_type="multipart/form-data", follow_redirects=True)
check("file upload saved", b"Form saved" in r.data)
with app.app_context():
    stored = dbq("SELECT value FROM data_values WHERE project_id=? AND"
                 " record_name='A1' AND field_name='scan'", (img_pid,), one=True)
check("file stored on disk", stored is not None and "xray.png" in stored["value"])
# download the file back
r = c.get(f"/p/{img_pid}/file/A1/scan")
check("file downloadable", r.status_code == 200 and r.data.startswith(b"\x89PNG"))
# entry page shows current file link
r = c.get(f"/p/{img_pid}/entry/A1/{img_iid}")
check("entry shows current file", b"xray.png" in r.data and b"Remove this file" in r.data)
# reject a disallowed extension
r = c.post(f"/p/{img_pid}/entry/A1/{img_iid}",
           data={"form_status": "complete",
                 "f_scan": (io.BytesIO(b"MZbad"), "evil.exe")},
           content_type="multipart/form-data")
check("bad file type rejected", b"not allowed" in r.data.lower())
# reject content that doesn't match its extension (html disguised as .png)
r = c.post(f"/p/{img_pid}/entry/A1/{img_iid}",
           data={"form_status": "complete",
                 "f_scan": (io.BytesIO(b"<html><script>x</script></html>"), "fake.png")},
           content_type="multipart/form-data")
check("disguised file content rejected", b"contents don't match" in r.data
      or b"contents don&#39;t match" in r.data)
# download carries nosniff header
r = c.get(f"/p/{img_pid}/file/A1/scan")
check("download sets nosniff", r.headers.get("X-Content-Type-Options") == "nosniff")
# export shows the human filename
r = c.get(f"/p/{img_pid}/export/data.csv")
check("file field exports filename", b"xray.png" in r.data)
# import template omits file fields
r = c.get(f"/p/{img_pid}/import/template")
check("import template omits file field", b"scan" not in r.data)
# an OPTIONAL file field can be uploaded then removed
r = c.post(f"/p/{img_pid}/designer/{img_iid}/field",
           data=dict(label="Extra photo", name="photo", field_type="file"),
           follow_redirects=True)
r = c.post(f"/p/{img_pid}/entry/A1/{img_iid}",
           data={"form_status": "complete",
                 "f_scan": (io.BytesIO(png), "xray.png"),
                 "f_photo": (io.BytesIO(png), "extra.png")},
           content_type="multipart/form-data", follow_redirects=True)
check("optional file uploaded", b"Form saved" in r.data)
r = c.post(f"/p/{img_pid}/entry/A1/{img_iid}",
           data={"form_status": "complete", "f_photo__remove": "1"},
           content_type="multipart/form-data", follow_redirects=True)
check("optional file removed", b"Form saved" in r.data)
with app.app_context():
    gone = dbq("SELECT value FROM data_values WHERE project_id=? AND"
               " record_name='A1' AND field_name='photo'", (img_pid,), one=True)
    kept = dbq("SELECT value FROM data_values WHERE project_id=? AND"
               " record_name='A1' AND field_name='scan'", (img_pid,), one=True)
check("removed file value cleared", gone is None)
check("required file still present", kept is not None and "xray.png" in kept["value"])

# ---- native statistical analysis (jamovi-style) + .sav export
r = c.post("/projects/new", data={"title": "Stats Project", "purpose": "research",
                                  "record_label": "ID"}, follow_redirects=True)
with app.app_context():
    st_pid = dbq("SELECT id FROM projects WHERE title='Stats Project'",
                 one=True)["id"]
    st_iid = dbq("SELECT id FROM instruments WHERE project_id=? ORDER BY position"
                 " LIMIT 1", (st_pid,), one=True)["id"]
for fld in [dict(label="Age", name="age", field_type="integer"),
            dict(label="Sex", name="sex", field_type="radio",
                 choices="1, Male | 2, Female"),
            dict(label="Arm", name="grp", field_type="radio", choices="1, A | 2, B"),
            dict(label="Score", name="score", field_type="number"),
            dict(label="Responder", name="outcome", field_type="yesno")]:
    c.post(f"/p/{st_pid}/designer/{st_iid}/field", data=fld, follow_redirects=True)
import random as _rnd
_rnd.seed(7)
_lines = ["record_id,age,sex,grp,score,outcome"]
for i in range(1, 41):
    _age = _rnd.randint(30, 80)
    _sex = _rnd.choice([1, 2])
    _grp = _rnd.choice([1, 2])
    _score = round(_age * 0.5 + (10 if _grp == 2 else 0) + _rnd.gauss(0, 5), 1)
    _out = 1 if _score > (_age * 0.5 + 5) else 0
    _lines.append(f"{i},{_age},{_sex},{_grp},{_score},{_out}")
_csv = "\n".join(_lines) + "\n"
r = c.post(f"/p/{st_pid}/import/upload",
           data={"file": (io.BytesIO(_csv.encode()), "stats.csv")},
           content_type="multipart/form-data")
_m = re.search(rb'name="token" value="([a-f0-9]+)"', r.data)
c.post(f"/p/{st_pid}/import/commit", data={"token": _m.group(1).decode()},
       follow_redirects=True)

base = f"/p/{st_pid}/analysis"
r = c.get(base + "?type=descriptives&vars=age&vars=score&vars=sex")
check("descriptives runs", b"Descriptive statistics" in r.data and b"Mean" in r.data)
r = c.get(base + "?type=frequencies&dep=sex")
check("frequencies runs", b"Frequencies" in r.data and b"Male" in r.data)
r = c.get(base + "?type=ttest&dep=score&group=grp")
check("t-test runs", b"t-test" in r.data and b"Mean difference" in r.data)
r = c.get(base + "?type=anova&dep=score&group=sex")
check("anova runs", b"ANOVA" in r.data and b"F" in r.data)
r = c.get(base + "?type=correlation&vars=age&vars=score")
check("correlation runs", b"correlation" in r.data.lower())
r = c.get(base + "?type=linear&dep=score&preds=age&preds=grp")
check("linear regression runs", b"R" in r.data and b"coefficients" in r.data.lower())
r = c.get(base + "?type=logistic&dep=outcome&preds=age")
check("logistic regression runs", b"Odds ratio" in r.data)
r = c.get(base + "?type=contingency&dep=sex&group=grp")
check("contingency runs", "χ²".encode() in r.data and b"Contingency" in r.data)
check("cross table shows column %", b"column %" in r.data)
# ---- Table One + summary (ClinicoPath-style tables)
r = c.get(base + "?type=tableone&group=outcome&vars=age&vars=sex&vars=score")
check("table one runs", b"Baseline characteristics" in r.data and b"Test" in r.data)
check("table one has a test column value",
      b"t-test" in r.data or b"Mann" in r.data or b"Chi-square" in r.data)
check("result tables have copy buttons", b"Copy for Word" in r.data and b">CSV<" in r.data)
r = c.get(base + "?type=tableone&group=age&vars=sex")
check("table one rejects a continuous group", b"continuous" in r.data)
r = c.get(base + "?type=summary&vars=age&vars=sex")
check("summary table runs", b"Summary of variables" in r.data)
r = c.get(base + "?type=summary")
check("summary defaults to all variables", b"Summary of variables" in r.data)
r = c.get(base + "?type=ttest&dep=score&group=sex_missing")
check("analysis handles bad input", r.status_code == 200)  # no crash

# .sav export opens in jamovi/SPSS/R
r = c.get(f"/p/{st_pid}/export/data.sav")
check("sav export served", r.status_code == 200 and r.data[:4] == b"$FL2")
import tempfile as _tf
import pyreadstat as _prs
_fh = _tf.NamedTemporaryFile(suffix=".sav", delete=False)
_fh.write(r.data)
_fh.close()
_sdf, _meta = _prs.read_sav(_fh.name)
check("sav has value labels", "sex" in _meta.variable_value_labels and
      _meta.variable_value_labels["sex"].get(1.0) == "Male")
check("sav has variable labels", _meta.column_names_to_labels.get("score") == "Score")
shutil.os.remove(_fh.name)

# P2: no .sav file left behind after export (PHI must not linger)
with app.app_context():
    _tmp = os.path.join(tmp, "tmp_imports")
    _left = [f for f in (os.listdir(_tmp) if os.path.isdir(_tmp) else [])
             if f.endswith(".sav")]
check("no .sav left on disk after export", _left == [])

# P3: checkbox fields expand to labelled 0/1 columns in .sav (project 1 has 'symptoms')
r = c.get("/p/1/export/data.sav")
_fh2 = _tf.NamedTemporaryFile(suffix=".sav", delete=False)
_fh2.write(r.data)
_fh2.close()
_cdf, _cmeta = _prs.read_sav(_fh2.name)
check("checkbox expanded in sav", "symptoms___1" in _cdf.columns)
check("checkbox column labelled",
      _cmeta.column_names_to_labels.get("symptoms___1", "").startswith("Symptoms"))
check("checkbox column has 0/1 value labels",
      _cmeta.variable_value_labels.get("symptoms___1", {}).get(1.0) == "Checked")
shutil.os.remove(_fh2.name)

# ---- delete a whole project (admin), with cascade
r = c.post("/projects/new", data={"title": "Throwaway", "purpose": "practice",
                                  "record_label": "ID"}, follow_redirects=True)
with app.app_context():
    tw_pid = dbq("SELECT id FROM projects WHERE title='Throwaway'", one=True)["id"]
c.post(f"/p/{tw_pid}/records/new", data={"record_name": "1"}, follow_redirects=True)
r = c.post(f"/p/{tw_pid}/delete", follow_redirects=True)
check("project deleted", b"permanently deleted" in r.data)
with app.app_context():
    gone = dbq("SELECT id FROM projects WHERE id=?", (tw_pid,), one=True)
    leftover = dbq("SELECT COUNT(*) n FROM records WHERE project_id=?",
                   (tw_pid,), one=True)["n"]
check("deleted project fully removed", gone is None and leftover == 0)

# ---- New Project page: both pre-build options removed, purpose explained
r = c.get("/projects/new")
check("template dropdown removed", b"Start from a template" not in r.data)
check("csv upload removed", b'name="csv_file"' not in r.data)
check("purpose explained", b"generalizable" in r.data)

# ---- suggestion datalists for instrument names + field labels
r = c.get("/p/1/designer")
check("instrument suggestions present", b"instr_suggest" in r.data)
r = c.get("/p/1/designer/1")
check("field label suggestions present", b"field_suggest" in r.data)

# ---- liquid glass theme assets present
_css = open("static/style.css", encoding="utf-8").read()
check("glass theme in css", '[data-theme="glass"]' in _css)
_js = open("static/app.js", encoding="utf-8").read()
check("theme cycles three", '"glass"' in _js and "THEMES" in _js)

# ---- production mode
c.get("/logout")
c.post("/login", data={"username": "admin", "password": "newpass123"})
r = c.post("/p/1/status", data={"target": "production"}, follow_redirects=True)
check("moved to production", b"PRODUCTION" in r.data)
r = c.post("/p/1/designer/1/field",
           data=dict(label="Late field", name="late", field_type="text"),
           follow_redirects=True)
check("design locked in production", b"Design is locked" in r.data)
r = c.post("/p/1/entry/1/1?event=1",
           data={"f_full_name": "Jane Doe", "f_age": "36", "f_sex": "2",
                 "f_symptoms": "1", "f_pregnant": "0",
                 "f_visit_date": "2026-07-01", "form_status": "complete"},
           follow_redirects=True)
check("data entry still allowed in production", b"Form saved" in r.data)

print()
if FAIL:
    print(f"{len(FAIL)} FAILURES:", FAIL)
    sys.exit(1)
print("ALL TESTS PASSED")
shutil.rmtree(tmp, ignore_errors=True)
