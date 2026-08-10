-- DataCapture SQLite schema
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name  TEXT NOT NULL DEFAULT '',
    email         TEXT NOT NULL DEFAULT '',
    is_admin      INTEGER NOT NULL DEFAULT 0,
    active        INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS projects (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL,
    purpose         TEXT NOT NULL DEFAULT 'research',
    specialty       TEXT NOT NULL DEFAULT '',
    notes           TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'dev',      -- dev | production
    is_longitudinal INTEGER NOT NULL DEFAULT 0,
    record_label    TEXT NOT NULL DEFAULT 'Record ID',
    created_by      INTEGER REFERENCES users(id),
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS project_users (
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id    INTEGER NOT NULL REFERENCES users(id)    ON DELETE CASCADE,
    role       TEXT NOT NULL DEFAULT 'data_entry',      -- admin | data_entry | read_only
    PRIMARY KEY (project_id, user_id)
);

CREATE TABLE IF NOT EXISTS instruments (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id          INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name                TEXT NOT NULL,                  -- machine name, unique per project
    label               TEXT NOT NULL,
    position            INTEGER NOT NULL DEFAULT 0,
    survey_enabled      INTEGER NOT NULL DEFAULT 0,
    survey_token        TEXT,
    survey_title        TEXT NOT NULL DEFAULT '',
    survey_instructions TEXT NOT NULL DEFAULT '',
    UNIQUE (project_id, name)
);

CREATE TABLE IF NOT EXISTS fields (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    instrument_id   INTEGER NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,                      -- variable name
    label           TEXT NOT NULL,
    field_type      TEXT NOT NULL DEFAULT 'text',
    choices         TEXT NOT NULL DEFAULT '',           -- "1, Male | 2, Female"
    validation      TEXT NOT NULL DEFAULT '',           -- integer|number|date|email|phone|''
    min_value       TEXT NOT NULL DEFAULT '',
    max_value       TEXT NOT NULL DEFAULT '',
    required        INTEGER NOT NULL DEFAULT 0,
    identifier      INTEGER NOT NULL DEFAULT 0,
    branching_logic TEXT NOT NULL DEFAULT '',
    field_note      TEXT NOT NULL DEFAULT '',
    position        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,                           -- machine name
    label      TEXT NOT NULL,
    position   INTEGER NOT NULL DEFAULT 0,
    UNIQUE (project_id, name)
);

CREATE TABLE IF NOT EXISTS event_instruments (
    event_id      INTEGER NOT NULL REFERENCES events(id)      ON DELETE CASCADE,
    instrument_id INTEGER NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
    PRIMARY KEY (event_id, instrument_id)
);

CREATE TABLE IF NOT EXISTS records (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    record_name TEXT NOT NULL,
    created_by  TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (project_id, record_name)
);

CREATE TABLE IF NOT EXISTS data_values (
    project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    record_name TEXT NOT NULL,
    event_id    INTEGER NOT NULL DEFAULT 0,             -- 0 = classic (non-longitudinal)
    field_name  TEXT NOT NULL,
    value       TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (project_id, record_name, event_id, field_name)
);
CREATE INDEX IF NOT EXISTS idx_data_proj_field ON data_values (project_id, field_name);

CREATE TABLE IF NOT EXISTS form_status (
    project_id    INTEGER NOT NULL,
    record_name   TEXT NOT NULL,
    event_id      INTEGER NOT NULL DEFAULT 0,
    instrument_id INTEGER NOT NULL,
    status        TEXT NOT NULL DEFAULT 'incomplete',   -- incomplete | unverified | complete
    PRIMARY KEY (project_id, record_name, event_id, instrument_id)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL DEFAULT (datetime('now')),
    username    TEXT NOT NULL DEFAULT '',
    project_id  INTEGER,
    record_name TEXT NOT NULL DEFAULT '',
    action      TEXT NOT NULL,
    details     TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_audit_proj ON audit_log (project_id, ts);
