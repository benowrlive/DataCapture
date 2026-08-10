# DataCapture

A standalone, REDCap-style electronic data capture (EDC) app for healthcare
research. Runs entirely on your own computer — your data never leaves it.

## Quick start (Windows)

1. Install Python 3.10+ from https://www.python.org/downloads/
   (tick **"Add Python to PATH"** during install).
2. Double-click **`Launch DataCapture.vbs`** (or its desktop shortcut).
   The first run installs dependencies into a local `.venv`, then your browser
   opens at `http://localhost:8710`. Use **`Stop DataCapture.vbs`** to shut it down.
3. The first screen asks you to create the **administrator account**.

Manual start (any OS):

```
pip install -r requirements.txt
python run.py
```

## Typical workflow (mirrors REDCap)

1. **New Project** → title, purpose, longitudinal on/off.
2. **Online Designer** → create instruments (forms) and their fields:
   text, numbers, dates, dropdown/radio/checkbox (with `code, label` choices),
   yes/no, sliders, section headers; validation, required/identifier flags and
   branching logic like `[sex] = '1' and [age] >= '18'`.
3. **Events** (longitudinal projects) → define Baseline / Week 4 / … and tick
   which instruments are collected at each event.
4. **User Rights** → add team accounts (created by the admin under *Users*)
   with Project Admin / Data Entry / Read Only roles.
5. Test with practice records, then **Move to Production** — design is locked.
6. Collect data:
   - staff enter records on the **Record Status Dashboard** (red/yellow/green
     status dots),
   - **surveys**: enable an instrument as a survey and share its public link,
   - **Data Import Tool**: download the CSV template, fill it, upload —
     errors are listed, overwrites are shown in red before you confirm.
7. **Export & Reports** → CSV (codes or labels), data dictionary, report
   tables, Stats & Charts. **Audit** shows who changed what and when.

## Sharing with your team on the local network

By default the app only listens on your own machine. To let colleagues (and
survey respondents) on the same network use it:

```
python run.py --host 0.0.0.0
```

Then give them `http://YOUR-PC-IP:8710` (find your IP with `ipconfig`).
Allow the port through Windows Firewall when prompted. Use this only on a
trusted clinic/office network.

## Backing up

Everything is stored in **`data/datacapture.db`** (SQLite). Copy this file
regularly to a safe place. To restore, stop the app and put the file back.
`data/secret_key` signs login cookies — keep it with your backup.

## Notes and limits

- Passwords are hashed; survey links use unguessable tokens; every change is
  written to the audit trail.
- This tool supports research data collection practice, but it is not, by
  itself, certified for regulated trials (e.g. 21 CFR Part 11 e-signatures).
- For disk-level protection of patient data, enable BitLocker (or equivalent)
  on the machine that stores the database.

## Project layout

See `docs/ARCHITECTURE.md` for the full structure, data model and workflow
diagrams.
