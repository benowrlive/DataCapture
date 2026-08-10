"""Database helpers: connection, schema bootstrap, audit logging."""
import os
import sqlite3
from flask import g, session

DATA_DIR = None  # set by create_app


def db_path():
    return os.path.join(DATA_DIR, "datacapture.db")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(db_path())
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(app):
    global DATA_DIR
    DATA_DIR = app.config["DATA_DIR"]
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(db_path())
    schema = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema, encoding="utf-8") as f:
        conn.executescript(f.read())
    _migrate(conn)
    conn.commit()
    conn.close()
    app.teardown_appcontext(close_db)


def _migrate(conn):
    """Add columns introduced after a database was first created.
    CREATE TABLE IF NOT EXISTS never alters an existing table, so new columns
    are added here. Each step is a no-op once the column exists."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(projects)")}
    if "specialty" not in cols:
        conn.execute(
            "ALTER TABLE projects ADD COLUMN specialty TEXT NOT NULL DEFAULT ''")


def q(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    rows = cur.fetchall()
    return (rows[0] if rows else None) if one else rows


def x(sql, args=()):
    """Execute + commit; returns lastrowid."""
    db = get_db()
    cur = db.execute(sql, args)
    db.commit()
    return cur.lastrowid


def pivot_values(pid):
    """The project's data as a lookup table plus its ordered record list.

    Returns (data, recs):
      data — {(record_name, event_id, field_name): value}
      recs — record rows ordered numerically then alphabetically.
    Single source of truth for reports, exports and analysis, so they can
    never disagree on keying or record order."""
    data = {}
    for r in q("SELECT record_name, event_id, field_name, value"
               " FROM data_values WHERE project_id=?", (pid,)):
        data[(r["record_name"], r["event_id"], r["field_name"])] = r["value"]
    recs = q("SELECT record_name FROM records WHERE project_id=?"
             " ORDER BY CAST(record_name AS INTEGER), record_name", (pid,))
    return data, recs


def audit(action, project_id=None, record_name="", details="", username=None):
    if username is None:
        username = session.get("username", "?")
    x(
        "INSERT INTO audit_log (username, project_id, record_name, action, details)"
        " VALUES (?,?,?,?,?)",
        (username, project_id, record_name, action, details[:2000]),
    )
