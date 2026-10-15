"""Spots table. Parameterized queries only (SR-18)."""
from .db import get_db


def insert(spot_id, label, status):
    get_db().execute(
        "INSERT INTO spots (id, label, status) VALUES (?, ?, ?)",
        (spot_id, label, status),
    )


def list_all():
    return get_db().execute("SELECT id, label, status FROM spots ORDER BY label").fetchall()


def list_with_status(status):
    return get_db().execute(
        "SELECT id, label, status FROM spots WHERE status = ? ORDER BY label",
        (status,),
    ).fetchall()


def get(spot_id):
    return get_db().execute(
        "SELECT id, label, status FROM spots WHERE id = ?", (spot_id,)
    ).fetchone()


def set_status(spot_id, status):
    get_db().execute("UPDATE spots SET status = ? WHERE id = ?", (status, spot_id))
