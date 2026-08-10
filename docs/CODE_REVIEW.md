# DataCapture — Code Quality & Maintainability Review

*Senior-engineer audit · scope: entire `D:\DataCapture` tree · goal: aggressive-but-safe simplification*

---

## 1. Verdict

The codebase is in **good shape for its size and stage**: ~3,900 lines of Python across small,
single-responsibility blueprint modules, ~1,500 lines of templates, one 580-line static bundle,
and a real end-to-end test (`test_e2e.py`) that exercises auth, design, entry, import/export and
production locking. Architecture is clean (Flask blueprints + a thin `db.py` + a validators layer).

The debt that exists is almost entirely **leftovers from features that were built and then removed
from the UI**, plus a handful of unused imports and one data-access pattern that is copy-pasted four
times. None of it is dangerous; all of it is worth clearing while the app is still small.

**What is *not* a problem (verified, so you don't over-cut):**

- All 27 templates are reachable. `entry.html` / `survey.html` are rendered via multi-line calls;
  `_form_fields.html` and `_help.html` are pulled in with `{% from … import %}`. No orphan templates.
- Every Flask view function that static analysis flagged as "unused" is a live route registered by a
  `@bp.route` decorator. Those are false positives.
- `run.py`, `reset_admin_password.py`, `validators.py`, `analysis.py`, `files.py`, the `.ico` files
  and the shortcut-creator scripts are all live or genuinely useful — keep them.

**Rough size of the cleanup:** ~255 lines of dead Python (two whole modules), ~80 more dormant lines
in `projects.py`, ~124 KB of stale release zips, ~8 unused imports/locals, and one 4-way duplication.

---

## 2. Findings at a glance

| # | Issue | Category | Impact if removed | Risk | Effort |
|---|-------|----------|-------------------|------|--------|
| 1 | `DataCapture_v1.0.zip`, `DataCapture_v1.1.zip` | Abandoned artifacts | −124 KB clutter | None | Trivial |
| 2 | `starter_templates.py` (dormant) | Dead/legacy code | −141 lines, −1 module | Low* | Small |
| 3 | `csv_template.py` + `_create_from_csv` (dormant) | Dead/legacy code | −114 lines + ~64 in projects.py | Low* | Small |
| 4 | `run_windows.bat` (superseded launcher) | Legacy code | −1 file, less confusion | Low | Trivial |
| 5 | Unused imports (`x`, `current_user`, `ROLE_LABELS`, `g`) | Dead code | Cleaner modules | None | Trivial |
| 6 | Dead locals in `reports.report()` (`events_by_id`, `used_events`) | Dead code | −2 lines + 1 query column | None | Trivial |
| 7 | `TAILORED_SPECIALTIES`, `files.ACCEPT` | Dead code | −2 unused names | None | Trivial |
| 8 | 4× copy-pasted `data_values` pivot | Duplicate logic | 1 helper vs 4 blocks | Low-Med | Medium |
| 9 | Context-pill Jinja block duplicated | Duplicate UI | 1 macro vs 2 copies | None | Trivial |
| 10 | `SELECT *` over-fetch in pivots | Redundant query | Slightly less I/O | Low | Folds into #8 |
| 11 | PowerShell/venv logic duplicated across scripts | Duplicate logic | Easier script upkeep | Low | Medium |
| 12 | `docs/ARCHITECTURE.md` drift | Tech debt | Accurate docs | None | Small |

\* "Low risk" = no runtime path or test reaches it; the only thing you lose is the ability to
re-enable the feature without pulling it back from git history or the v1.1 zip.

---

## 3. Detailed findings

### Tier 1 — Safe deletions (do these first)

#### 3.1 Old release zips — `DataCapture_v1.0.zip`, `DataCapture_v1.1.zip`
- **Why unnecessary:** Point-in-time snapshots of earlier builds (you're on v1.2.0 now). They are not
  referenced by any code and are not how the app runs.
- **Impact:** Removes ~124 KB and, more importantly, removes the temptation to edit or ship an old copy
  by accident.
- **Risk:** None. If you want frozen backups, they belong outside the working folder (or in git tags),
  not beside the live source.
- **Plan:** Move them to a backup location or delete. (On this machine I can only *move* files, so I'd
  relocate them to a `_to_delete/` folder for you to remove.)

#### 3.2 Dormant "starter template" engine — `starter_templates.py`
- **Why unnecessary:** This module (the SBO registry template, `TEMPLATES`, `TEMPLATE_CHOICES`,
  `apply_template`) is only referenced by `projects.py`. But the New Project form no longer has the
  template dropdown, so the `template` field is never posted → `tpl` is always `None` → `apply_template`
  is never called, and `TEMPLATE_CHOICES` is passed to `project_new.html`, which no longer reads it.
- **Impact:** Deleting the module and its wiring removes ~141 lines and cuts `projects.py`'s imports and
  its dead `if tpl:` branch (~15 lines).
- **Risk:** Low, with one nuance — the code is *dormant, not unreachable*: a hand-crafted multipart POST
  could still trigger it, so it's an untested path that isn't covered by any test. Removing it eliminates
  that. The only real loss is the built-in SBO starter template.
- **Plan:** If you want "start from a template" as a real feature again, re-expose it in the UI instead of
  leaving it dead. Otherwise delete `starter_templates.py`, drop its import, remove the `tpl`/`apply_template`
  branch, and drop `templates=TEMPLATE_CHOICES` from the `project_new.html` render. Re-run `test_e2e.py`.

#### 3.3 Dormant "create project from CSV" engine — `csv_template.py` + `_create_from_csv`
- **Why unnecessary:** `csv_template.parse_csv` is called only by `_create_from_csv`, which runs only when
  a `csv_file` is uploaded. The New Project form has no file input and isn't even `multipart/form-data`, so
  this never fires from the UI.
- **Impact:** Removes `csv_template.py` (~114 lines) plus `_create_from_csv` in `projects.py` (~64 lines) —
  the single biggest chunk of dead logic in the app.
- **Risk:** Low (same "dormant not unreachable" nuance as 3.2). Note: the **Import Data** feature is a
  *different*, live subsystem (`importexport.py`) — do not confuse the two. This finding is only about
  *creating a project from a CSV's headers*, which was removed from New Project.
- **Plan:** Of the two dormant engines, CSV-from-headers is the more likely to come back. Decide: either
  re-expose it as its own button (and keep the module, add a test), or delete `csv_template.py` +
  `_create_from_csv` + the `csv_file` branch. Re-run tests.

#### 3.4 Superseded launcher — `run_windows.bat`
- **Why unnecessary:** It's the original visible-console launcher (create venv → install deps → `python run.py`
  → pause). The app now starts through `Launch DataCapture.vbs → start_datacapture.ps1 → server_hidden.py`,
  which does the same venv/dependency bootstrap itself. `run_windows.bat` is the only thing that calls `run.py`
  from the shipped launchers.
- **Impact:** One fewer "which file do I double-click?" question, and it removes a duplicated copy of the
  venv/dep-install logic.
- **Risk:** Low. Keep `run.py` — it's still the clean way to run from a terminal or share on a clinic LAN
  (`python run.py --host 0.0.0.0`). Only the `.bat` wrapper is redundant.
- **Plan:** Delete `run_windows.bat`. Keep `run.py`, `Launch DataCapture.vbs`, `Start DataCapture.bat`
  (console fallback for troubleshooting) and the stop scripts.

#### 3.5 Unused imports (confirmed by pyflakes)
- `importexport.py` — `x` imported from `.db`, never used (and shadowed by a list-comprehension variable `x`
  later in `_codes`).
- `projects.py` — `current_user` and `ROLE_LABELS` imported from `.auth`, never used.
- `surveys.py` — `g` (from flask) and `x` (from `.db`) imported, never used.
- **Why unnecessary:** Pure noise; they imply dependencies that don't exist.
- **Impact/Risk:** Cleaner import lists, zero behavior change, no risk.
- **Plan:** Delete the four names. Rename the `_codes` comprehension variable so nothing shadows anything.
  `python -m pyflakes datacapture/*.py` should then be clean.

#### 3.6 Dead locals in `reports.report()`
- **Why unnecessary:** `events_by_id` (line 31) is built and never read (the row loop uses `e["label"]`
  directly). `used_events` (lines 35/38) is created and `.add()`-ed to but never consumed.
- **Impact:** Two dead lines; also lets the value query drop a column (see 3.10).
- **Risk:** None.
- **Plan:** Delete both; keep the `data[...] = value` pivot.

#### 3.7 Unused module-level names — `TAILORED_SPECIALTIES`, `files.ACCEPT`
- **Why unnecessary:** `specialties.TAILORED_SPECIALTIES` was added "for UI messaging" but is never referenced.
  `files.ACCEPT` duplicates the `accept="…"` string that `_form_fields.html` already hardcodes, and the
  constant itself is never used.
- **Impact/Risk:** Two dead names removed; none.
- **Plan:** Delete `TAILORED_SPECIALTIES`. For `ACCEPT`, either delete it, or (better, see 3.14) make it the
  single source of truth and have the template read it — don't keep both the constant and the hardcoded copy.

---

### Tier 2 — Consolidation (higher value, a little more care)

#### 3.8 The `data_values` pivot is copy-pasted four times *(highest-value refactor)*
- **Where:** `reports.py` (`report`), `importexport.py` (`export_data` and `_sav_frame`), `analysis.py`
  (`get_dataframe`). All four run essentially:
  ```python
  data = {}
  for r in q("SELECT * FROM data_values WHERE project_id=?", (pid,)):
      data[(r["record_name"], r["event_id"], r["field_name"])] = r["value"]
  # + the same "recs ORDER BY CAST(record_name AS INTEGER)" query
  ```
- **Why it's debt:** Four independent copies of your core read model. A change to how values are keyed,
  how records are ordered, or how events are handled must be made in four places or they silently diverge —
  and export vs report vs analysis are exactly the places you don't want to disagree.
- **Impact of consolidating:** One helper (e.g. `db.pivot_values(pid)` returning `(values_dict, record_list)`)
  replaces four blocks; every consumer gets the same ordering and keying for free; future optimizations happen
  once.
- **Risk:** Low-to-medium — it touches export, reports and analysis. All three are covered by `test_e2e.py`,
  so a regression shows up immediately.
- **Plan:** Add the helper to `db.py` (or a small `dataset.py`), refactor the four call sites, run the suite.

#### 3.9 Context-pill block duplicated in two templates
- **Where:** the identical `{% if g.project.specialty or g.project.purpose %} … pills … {% endif %}` appears in
  `project_setup.html` and `export.html` (added when the specialty feature landed).
- **Plan:** Move it into a `{% macro project_context() %}` (in `_suggest.html` or a new `_bits.html`) and call it
  in both places. Trivial, no risk.

#### 3.10 `SELECT *` over-fetch in the pivots
- **Why:** The pivot queries `SELECT *` from `data_values` but use only `record_name, event_id, field_name, value`
  (as `export_data` at line 157 already does correctly). Pulling `id`/`project_id` and any future columns is wasted I/O.
- **Impact:** Minor performance win at scale; mostly a consistency fix.
- **Plan:** Select only the four columns — naturally handled when you build the shared helper in 3.8.

#### 3.11 Duplicated shell/PowerShell bootstrap
- **Where:** `Get-DataCapturePids` / `Test-DataCapturePort` are copied between `start_datacapture.ps1` and
  `stop_datacapture.ps1`; the venv-create + dependency-install block is repeated across `run_windows.bat`
  (going away in 3.4), `reset_password.bat`, and `start_datacapture.ps1`.
- **Why it's debt:** Fixing the port-detection logic (or the dependency list) means editing several files.
- **Risk:** Low, but standalone double-click scripts sometimes duplicate on purpose (each must stand alone).
- **Plan (optional):** Factor the shared PowerShell functions into a `_dc_common.ps1` that the two `.ps1`
  scripts dot-source. Leave the `.bat` files alone unless you're consolidating launchers anyway.

---

### Tier 3 — Lower priority

#### 3.12 `docs/ARCHITECTURE.md` may have drifted
- It predates the statistics engine, the specialty feature and the new launcher/hot-reload behavior.
- **Plan:** Refresh it (or let me regenerate it) once the deletions above are done, so the docs match reality.

#### 3.13 Redundant alternative launchers (informational)
- `Start DataCapture.bat` (visible console) and `Launch DataCapture.vbs` (hidden) both run the same PS1.
  This is mild redundancy, but the console version is genuinely useful for troubleshooting a failed start,
  so I recommend **keeping both** and simply being clear in the README which is the day-to-day icon.

---

## 4. Recommended cleanup order (safe path)

1. **Zips** — relocate/delete `DataCapture_v1.0.zip`, `DataCapture_v1.1.zip`. *(Zero risk.)*
2. **Mechanical dead code** — remove the unused imports (3.5), dead locals (3.6), `TAILORED_SPECIALTIES`
   and `ACCEPT` (3.7). Run `test_e2e.py` + `pyflakes`. *(Zero risk.)*
3. **Decide on the two dormant features** (3.2 template, 3.3 CSV-from-headers): re-expose in the UI *or*
   delete the module + wiring. Then run tests. *(Low risk; this is the big line-count win.)*
4. **Legacy launcher** — delete `run_windows.bat` (3.4). *(Low risk; keep `run.py`.)*
5. **Consolidate the pivot** into one helper and refactor the four call sites (3.8 + 3.10); run tests.
6. **Extract the context-pill macro** (3.9).
7. *(Optional)* PowerShell dedup (3.11), refresh `ARCHITECTURE.md` (3.12).

Every step is independently shippable, and every step ends with `python test_e2e.py` as the gate.

## 5. Guardrails before deleting anything

- **Back up first:** copy `data\datacapture.db` (your real data is never touched by any of this, but back it up
  anyway) and, ideally, snapshot the whole folder / commit to git so deletions are reversible.
- **Gate on the test suite:** `test_e2e.py` covers auth, designer, records, import, export (CSV + `.sav`),
  reports/stats, and production locking. Run it after each step; if it passes, the change is safe.
- **Steps 1–2, 4 are reversible-in-practice and carry no behavioral risk.** Step 3 is the only one that removes
  a *capability*, so make the keep-or-cut decision deliberately.
