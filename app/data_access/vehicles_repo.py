"""Vehicles table. Parameterized queries only (SR-18).

Every query that reads or changes one driver's vehicles includes
"owner_id = ?", so a driver can only ever reach their own vehicles (SR-08).
"""
from .db import get_db


def insert(vehicle_id, owner_id, plate_enc, created_at):
    get_db().execute(
        "INSERT INTO vehicles (id, owner_id, plate_enc, created_at) VALUES (?, ?, ?, ?)",
        (vehicle_id, owner_id, plate_enc, created_at),
    )


def list_plate_ciphertexts():
    """All encrypted plates, used to check that a new plate is unique (FR-04)
    and to find the vehicle at the gate (FR-09)."""
    return get_db().execute("SELECT id, plate_enc FROM vehicles").fetchall()


def list_for_owner(owner_id):
    return get_db().execute(
        "SELECT id, plate_enc, created_at FROM vehicles WHERE owner_id = ?"
        " ORDER BY created_at",
        (owner_id,),
    ).fetchall()


def get_plate_ciphertext(vehicle_id):
    """The encrypted plate of one vehicle, for a support agent through an open
    dispute (SR-09). The caller checks the dispute first."""
    row = get_db().execute(
        "SELECT plate_enc FROM vehicles WHERE id = ?", (vehicle_id,)
    ).fetchone()
    return row["plate_enc"] if row else None


def get_for_owner(vehicle_id, owner_id):
    return get_db().execute(
        "SELECT id FROM vehicles WHERE id = ? AND owner_id = ?",
        (vehicle_id, owner_id),
    ).fetchone()


def delete_for_owner(vehicle_id, owner_id):
    """Returns the number of deleted rows: 0 if the vehicle is not this owner's."""
    cursor = get_db().execute(
        "DELETE FROM vehicles WHERE id = ? AND owner_id = ?",
        (vehicle_id, owner_id),
    )
    return cursor.rowcount
