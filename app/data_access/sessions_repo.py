"""Login sessions table. Parameterized queries only (SR-15)."""
from .db import get_db


def insert(token_hash, user_id, at):
    get_db().execute(
        "INSERT INTO login_sessions (token_hash, user_id, created_at, last_seen_at)"
        " VALUES (?, ?, ?, ?)",
        (token_hash, user_id, at, at),
    )


def get_with_role(token_hash):
    """The session and the user's current role.

    The role is read from the users table on every request, never from the
    cookie or the request, so a client cannot change its own role (FR-02).
    """
    return get_db().execute(
        "SELECT s.user_id, s.last_seen_at, u.role"
        " FROM login_sessions s JOIN users u ON u.id = s.user_id"
        " WHERE s.token_hash = ?",
        (token_hash,),
    ).fetchone()


def touch(token_hash, at):
    get_db().execute(
        "UPDATE login_sessions SET last_seen_at = ? WHERE token_hash = ?",
        (at, token_hash),
    )


def delete(token_hash):
    get_db().execute("DELETE FROM login_sessions WHERE token_hash = ?", (token_hash,))
