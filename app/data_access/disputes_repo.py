"""Disputes table. Parameterized queries only (SR-15).

Queries for one driver include "driver_id = ?" (SR-05).
"""
from .db import get_db


def insert(dispute_id, driver_id, reservation_id, parking_session_id, reason, created_at):
    get_db().execute(
        "INSERT INTO disputes"
        " (id, driver_id, reservation_id, parking_session_id, reason, status, created_at)"
        " VALUES (?, ?, ?, ?, ?, 'OPEN', ?)",
        (dispute_id, driver_id, reservation_id, parking_session_id, reason, created_at),
    )


def has_open_for_record(reservation_id, parking_session_id):
    """True if the reservation or parking session already has an open dispute.
    "IS ?" also matches NULL, so the unused one of the two IDs is ignored."""
    row = get_db().execute(
        "SELECT COUNT(*) AS n FROM disputes WHERE status = 'OPEN'"
        " AND reservation_id IS ? AND parking_session_id IS ?",
        (reservation_id, parking_session_id),
    ).fetchone()
    return row["n"] > 0


def list_for_driver(driver_id):
    return get_db().execute(
        "SELECT id, driver_id, reservation_id, parking_session_id, reason, status, created_at,"
        " closed_at FROM disputes WHERE driver_id = ? ORDER BY created_at DESC",
        (driver_id,),
    ).fetchall()


def list_open():
    return get_db().execute(
        "SELECT id, driver_id, reservation_id, parking_session_id, reason, status, created_at,"
        " closed_at FROM disputes WHERE status = 'OPEN' ORDER BY created_at",
    ).fetchall()


def driver_has_open(driver_id):
    """SR-06: the condition for a support agent to see a driver's data."""
    row = get_db().execute(
        "SELECT COUNT(*) AS n FROM disputes WHERE driver_id = ? AND status = 'OPEN'",
        (driver_id,),
    ).fetchone()
    return row["n"] > 0


def get_status(dispute_id):
    row = get_db().execute(
        "SELECT status FROM disputes WHERE id = ?", (dispute_id,)
    ).fetchone()
    return row["status"] if row else None


def close(dispute_id, closed_at):
    """Returns 1 if an open dispute was closed, 0 otherwise."""
    cursor = get_db().execute(
        "UPDATE disputes SET status = 'CLOSED', closed_at = ?"
        " WHERE id = ? AND status = 'OPEN'",
        (closed_at, dispute_id),
    )
    return cursor.rowcount


def delete_expired(cutoff):
    """PR-09: delete disputes that were closed before the cutoff."""
    cursor = get_db().execute(
        "DELETE FROM disputes WHERE status = 'CLOSED' AND closed_at < ?",
        (cutoff,),
    )
    return cursor.rowcount
