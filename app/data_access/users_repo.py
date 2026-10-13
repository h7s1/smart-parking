"""Users table. Parameterized queries only (SR-15)."""
from .db import get_db


def insert(user_id, email_enc, password_hash, role, created_at):
    get_db().execute(
        "INSERT INTO users (id, email_enc, password_hash, role, created_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (user_id, email_enc, password_hash, role, created_at),
    )


def list_email_ciphertexts():
    """IDs and encrypted emails of all users.

    The team's design finds a user by decrypting each email and comparing it
    (Personal Data Map, AI interaction 2). Known limitation: this reads every
    row on each login, which only suits a small data set.
    """
    return get_db().execute("SELECT id, email_enc FROM users").fetchall()


def get(user_id):
    return get_db().execute(
        "SELECT id, email_enc, password_hash, role, failed_logins, locked_until"
        " FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()


def set_failed_logins(user_id, failed_logins, locked_until):
    get_db().execute(
        "UPDATE users SET failed_logins = ?, locked_until = ? WHERE id = ?",
        (failed_logins, locked_until, user_id),
    )


def record_successful_login(user_id, at):
    get_db().execute(
        "UPDATE users SET failed_logins = 0, locked_until = NULL, last_login_at = ?"
        " WHERE id = ?",
        (at, user_id),
    )


def delete(user_id):
    """Deletes the user. ON DELETE CASCADE in schema.sql also deletes the user's
    vehicles, reservations, parking sessions, disputes and login sessions (PR-11)."""
    get_db().execute("DELETE FROM users WHERE id = ?", (user_id,))


def list_inactive(cutoff):
    """Accounts with no login since the cutoff (or never, if created before it).

    An account whose car is parked right now is skipped, so deleting it does
    not leave a spot OCCUPIED.
    """
    return get_db().execute(
        "SELECT id FROM users"
        " WHERE COALESCE(last_login_at, created_at) < ?"
        " AND NOT EXISTS (SELECT 1 FROM parking_sessions ps"
        "                 JOIN vehicles v ON v.id = ps.vehicle_id"
        "                 WHERE v.owner_id = users.id AND ps.exit_time IS NULL)",
        (cutoff,),
    ).fetchall()
