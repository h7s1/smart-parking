"""Database connection and transactions.

The data access layer is the only code that talks to the database (Figure 1).
Every query in this package uses ? placeholders, so input is sent to SQLite as
data and can never change the SQL itself (SR-15). Never build SQL with
f-strings, + or % formatting.
"""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from flask import current_app, g

SCHEMA_FILE = Path(__file__).with_name("schema.sql")


def connect(path):
    # isolation_level=None: each statement commits on its own, and we open a
    # transaction explicitly (see transaction()) when several must succeed together.
    conn = sqlite3.connect(path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db():
    """One connection per request, closed by close_db() when the request ends."""
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def create_schema(conn):
    conn.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))


@contextmanager
def transaction(immediate=False):
    """Run several statements as one unit: all succeed, or none are saved.

    immediate=True takes the write lock at the start, so two requests cannot
    check and insert at the same time (used to stop double bookings, NFR-09).
    """
    conn = get_db()
    conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
    try:
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
