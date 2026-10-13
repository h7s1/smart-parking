"""Parking sessions table (the parking history). Parameterized queries only (SR-15).

A session holds the vehicle ID, the spot and the entry and exit times, never a
plate or email (PR-05). Queries for one driver go through the vehicles table
and include "owner_id = ?" (SR-05).
"""
from .db import get_db


def insert(session_id, vehicle_id, spot_id, entry_time):
    get_db().execute(
        "INSERT INTO parking_sessions (id, vehicle_id, spot_id, entry_time)"
        " VALUES (?, ?, ?, ?)",
        (session_id, vehicle_id, spot_id, entry_time),
    )


def get_open_for_vehicle(vehicle_id):
    """The session of a car that is still inside (no exit time yet), or None."""
    return get_db().execute(
        "SELECT id, spot_id FROM parking_sessions"
        " WHERE vehicle_id = ? AND exit_time IS NULL",
        (vehicle_id,),
    ).fetchone()


def close(session_id, exit_time):
    get_db().execute(
        "UPDATE parking_sessions SET exit_time = ? WHERE id = ? AND exit_time IS NULL",
        (exit_time, session_id),
    )


def owner_has_open_session(owner_id):
    """True if one of this driver's cars is parked right now."""
    row = get_db().execute(
        "SELECT COUNT(*) AS n FROM parking_sessions ps"
        " JOIN vehicles v ON v.id = ps.vehicle_id"
        " WHERE v.owner_id = ? AND ps.exit_time IS NULL",
        (owner_id,),
    ).fetchone()
    return row["n"] > 0


def list_for_owner(owner_id):
    return get_db().execute(
        "SELECT ps.id, ps.vehicle_id, ps.entry_time, ps.exit_time, s.label AS spot_label"
        " FROM parking_sessions ps"
        " JOIN vehicles v ON v.id = ps.vehicle_id"
        " JOIN spots s ON s.id = ps.spot_id"
        " WHERE v.owner_id = ? ORDER BY ps.entry_time DESC",
        (owner_id,),
    ).fetchall()


def get_for_owner(session_id, owner_id):
    return get_db().execute(
        "SELECT ps.id FROM parking_sessions ps"
        " JOIN vehicles v ON v.id = ps.vehicle_id"
        " WHERE ps.id = ? AND v.owner_id = ?",
        (session_id, owner_id),
    ).fetchone()


def delete_expired(cutoff):
    """PR-07: delete sessions that entered before the cutoff, unless they are
    linked to an open dispute. A session with no exit time (the car is still
    inside) is kept until the car leaves, so its spot is not left OCCUPIED."""
    cursor = get_db().execute(
        "DELETE FROM parking_sessions"
        " WHERE entry_time < ? AND exit_time IS NOT NULL"
        " AND NOT EXISTS (SELECT 1 FROM disputes d"
        "                 WHERE d.parking_session_id = parking_sessions.id"
        "                 AND d.status = 'OPEN')",
        (cutoff,),
    )
    return cursor.rowcount
