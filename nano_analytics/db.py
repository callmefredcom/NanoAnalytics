import sqlite3
from flask import g, current_app

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS hits (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      INTEGER NOT NULL,
    site    TEXT NOT NULL,
    path    TEXT NOT NULL,
    ref     TEXT,
    ua      TEXT,
    lang    TEXT,
    w       INTEGER,
    session TEXT,
    country TEXT
);

CREATE INDEX IF NOT EXISTS idx_site_ts ON hits(site, ts);
"""


def get_db():
    """Return a per-request SQLite connection stored on Flask's g object."""
    if "_db" not in g:
        g._db = sqlite3.connect(
            current_app.config["DB_PATH"],
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        g._db.row_factory = sqlite3.Row
    return g._db


def close_db(e=None):
    db = g.pop("_db", None)
    if db is not None:
        db.close()


def init_db(app):
    """Called once at startup to create schema if not present."""
    with app.app_context():
        db = get_db()
        db.executescript(SCHEMA)
        # Non-destructive migration: add country column to existing databases
        try:
            db.execute("ALTER TABLE hits ADD COLUMN country TEXT")
            db.commit()
        except Exception:
            pass  # column already exists
