"""Audit log table. Parameterized queries only (SR-15).

There is no update function, and no delete function: entries can only be
added and read. The database triggers in schema.sql also block changes
(PROPOSED-3). Deleting entries older than 180 days (PR-10) will be added with
the cleanup job in a later phase.
"""
from .db import get_db


def insert(entry_id, user_id, action, target_id, ip_address, created_at):
    get_db().execute(
        "INSERT INTO audit_log (id, user_id, action, target_id, ip_address, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (entry_id, user_id, action, target_id, ip_address, created_at),
    )


def list_recent(limit):
    return get_db().execute(
        "SELECT created_at, action, user_id, target_id, ip_address FROM audit_log"
        " ORDER BY created_at DESC, rowid DESC LIMIT ?",
        (limit,),
    ).fetchall()
