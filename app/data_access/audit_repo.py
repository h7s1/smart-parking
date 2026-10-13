"""Audit log table. Parameterized queries only (SR-15).

There is no update function. The only delete is delete_expired(), used by the
cleanup job for entries older than 180 days (PR-10). The database triggers in
schema.sql also block changes and early deletes (SR-23).
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


def delete_expired(cutoff, retention_days):
    """PR-10: delete entries created before the cutoff.

    The second condition repeats the 180-day rule with the database's own
    clock, the same rule the trigger in schema.sql enforces, so this delete
    can never be blocked half-way by the trigger.
    """
    cursor = get_db().execute(
        "DELETE FROM audit_log WHERE created_at < ?"
        " AND created_at <= strftime('%Y-%m-%d %H:%M:%S', 'now', ?)",
        (cutoff, f"-{int(retention_days)} days"),
    )
    return cursor.rowcount
