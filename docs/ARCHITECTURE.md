# DataCapture — Architecture, Structure & Workflow

A standalone, REDCap-style healthcare data collection app.
Runs as a local web application on one Windows PC (Python + Flask + SQLite),
openable in any browser, and shareable across a clinic LAN when desired.

Design references: the REDCap tutorial by Braz et al., *Healthcare Informatics
Research* 2021 (DOI: 10.4258/hir.2021.27.4.341), and Temple University's
REDCap library guide (Data Import Tool, Longitudinal Data Collection,
Development vs. Production, Surveys).

---

## 1. Design principles (borrowed from REDCap)

1. **Project-centric** — every study is a *Project*; all instruments, events,
   records, users and logs are scoped to a project.
2. **Instruments as metadata** — data collection forms ("instruments") are not
   hard-coded; they are rows in a `fields` table (the *data dictionary*).
   The entry UI is rendered from metadata at runtime.
3. **EAV data storage** — collected values are stored as
   (record, event, field, value) tuples, exactly like REDCap's `redcap_data`
   table. This lets any project change its instruments without schema changes.
4. **Development → Production lifecycle** — a project starts in Development
   (design freely, test data allowed). Moving to Production locks structural
   design changes to protect real data.
5. **Least-privilege user rights** — per-project roles (Project Admin,
   Data Entry, Read Only) plus a global Administrator.
6. **Everything is audited** — every login, record change, import and design
   change writes to an append-only audit log.
7. **Offline-first** — no CDN, no internet dependency. All CSS/JS is local.
   The only network involved is your own machine (or LAN if you share it).

## 2. Technology stack

| Layer      | Choice                        | Why |
|------------|-------------------------------|-----|
| Language   | Python 3.10+                  | Readable, easy for the team to extend |
| Web        | Flask 3 (built-in dev server / waitress) | Minimal, battle-tested |
| Database   | SQLite (single file `data/datacapture.db`) | Zero admin, easy backup = copy one file |
| Frontend   | Server-rendered Jinja2 + vanilla JS + one CSS file | Fully offline, no build step |
| Charts     | Inline SVG generated server-side | No JS library needed |
| Passwords  | PBKDF2 (werkzeug)             | Standard, no extra deps |

## 3. Folder structure

```
DataCapture/
├── run.py                  # entry point: starts server, opens browser
├── run_windows.bat         # double-click launcher for Windows
├── requirements.txt        # flask, waitress
├── README.md               # install & user guide
├── docs/
│   └── ARCHITECTURE.md     # this file
├── datacapture/            # application package
│   ├── __init__.py         # app factory, blueprint registration
│   ├── db.py               # SQLite connection, schema bootstrap, audit()
│   ├── schema.sql          # full database schema
│   ├── auth.py             # login/logout, sessions, role decorators
│   ├── admin.py            # global user management
│   ├── projects.py         # project CRUD, setup page, production mode
│   ├── designer.py         # online designer: instruments + fields, codebook
│   ├── events.py           # longitudinal events & instrument-event mapping
│   ├── records.py          # record home, data entry forms, save logic
│   ├── surveys.py          # public survey links (no login)
│   ├── importexport.py     # CSV template, validated import, exports
│   ├── reports.py          # data views, stats & charts
│   └── validators.py       # field validation + branching-logic evaluator
├── templates/              # Jinja2 pages (base.html + one per screen)
├── static/
│   ├── style.css
│   └── app.js              # branching logic, designer interactions
└── data/                   # created at first run
    └── datacapture.db      # ALL your data lives here — back this file up
```

## 4. Data model (schema overview)

```
users            id, username, password_hash, display_name, email,
                 is_admin, active, created_at
projects         id, title, purpose, notes, status(dev|production),
                 is_longitudinal, record_label, created_by, created_at
project_users    project_id, user_id, role(admin|data_entry|read_only)
instruments      id, project_id, name, label, position,
                 survey_enabled, survey_token, survey_title, survey_instructions
fields           id, instrument_id, name, label, field_type, choices,
                 validation, required, identifier, branching_logic,
                 field_note, position
events           id, project_id, name, label, position        (longitudinal)
event_instruments event_id, instrument_id                     (mapping grid)
records          id, project_id, record_name, created_by, created_at
data_values      project_id, record_id, event_id, field_name, value
form_status      record_id, event_id, instrument_id,
                 status(incomplete|unverified|complete)
audit_log        id, ts, user_id, project_id, record_name, action, details
```

**Field types:** `text`, `notes`, `integer`, `number`, `date`, `time`,
`email`, `phone`, `dropdown`, `radio`, `checkbox`, `yesno`, `truefalse`,
`slider`, `descriptive` (display-only), `section_header`.

**Choices format** (same as REDCap): `1, Male | 2, Female | 3, Other` —
the *code* is stored, the *label* is displayed. Imports must supply codes,
exactly as the Temple guide describes.

**Branching logic** (subset of REDCap syntax):
`[sex] = '1' and [age] >= '18'` — supported operators: `=`, `<>`, `>`, `>=`,
`<`, `<=`, `and`, `or`, parentheses. Evaluated both live in the browser
(app.js) and server-side on save (validators.py).

## 5. Application workflow

### 5.1 Study lifecycle (mirrors the REDCap tutorial)

```
Create project ──► Design instruments ──► Define events (if longitudinal)
      │                (Online Designer)        │
      ▼                                         ▼
 Add team users ◄─────────────────── Map instruments to events
      │
      ▼
 Test with practice records  ──►  Review codebook / dictionary export
      │
      ▼
 Move to PRODUCTION  (design locked; admin can revert)
      │
      ▼
 Collect data:  staff data entry  +  public survey links  +  CSV import
      │
      ▼
 Monitor:  reports, stats & charts, audit trail
      │
      ▼
 Export: CSV (codes or labels), data dictionary, per-instrument extracts
      │
      ▼
 Backup: copy data/datacapture.db  (automated reminder on dashboard)
```

### 5.2 Data entry workflow

1. **Record Home** — grid of records × (events ×) instruments with
   colored status dots (red = incomplete, yellow = unverified,
   green = complete), like REDCap's Record Status Dashboard.
2. Click a cell → rendered entry form for that instrument/event.
3. Client-side: required checks, type validation, live branching logic.
4. Server-side: everything re-validated; each changed value writes an
   audit row (old value → new value).
5. Form marked Incomplete / Unverified / Complete at the bottom.

### 5.3 Survey workflow (public respondents)

1. Project admin enables an instrument as a survey → app generates an
   unguessable token URL: `http://<your-ip>:8710/s/<token>`.
2. Respondent opens the link (no login), completes the form, submits.
3. A new record is auto-created (next record number), values saved,
   form status set to Complete, audit row written as user "survey".
4. Thank-you page shown. Optional: survey can also be filled for an
   existing record from the record home.

### 5.4 CSV import workflow (modeled on the Temple guide)

1. Download the **Import Template** (records-as-rows): header row =
   `record_id` + every variable name in the project
   (`<event>.<variable>` when longitudinal).
2. Fill it in Excel; for dropdown/radio/checkbox supply the **numeric
   code**, not the label.
3. Upload → the app validates every cell (type, range, valid category).
4. **Errors table** (record, field, value, message) shown in red if any —
   nothing is imported until all rows pass.
5. If valid: **review table** — new values in black, values that would
   **overwrite** existing data highlighted in red, so you never overwrite
   unintentionally.
6. Confirm → data committed, one audit row per changed value.

### 5.5 Users & rights workflow

- Global **Administrator** creates user accounts (first-run wizard creates
  the initial admin).
- Inside each project, the project admin grants roles:
  - **Project Admin** — design, users, production mode, delete records
  - **Data Entry** — create/edit records, use import tool
  - **Read Only** — view records, reports, exports only
- In Production, structural changes are blocked for everyone;
  a global admin may revert the project to Development (audited).

## 6. Security posture (standalone context)

- Passwords hashed (PBKDF2-SHA256); sessions via signed cookies with a
  per-install random secret.
- Survey URLs use 32-char random tokens; survey routes are the only
  unauthenticated routes and can only write to their own instrument.
- SQLite file lives in `data/` — encrypt the disk (BitLocker) for data
  at rest; the app itself binds to localhost by default. To share on the
  LAN, start with `--host 0.0.0.0` (documented in README).
- This is a research data tool, not a certified medical device; for
  regulated trials (21 CFR Part 11) additional controls (e-signatures,
  validated hosting) would be phase-3 work.

## 7. Roadmap after v1

- Phase 2: calculated fields & piping, matrix/Likert groups, repeat
  instruments, per-field export de-identification, scheduled backups,
  record locking/e-signatures, PDF of blank/completed instruments.
- Phase 3: multi-site LAN deployment behind HTTPS, REST API
  (REDCap-style token API), mobile-offline entry, e-consent framework.
