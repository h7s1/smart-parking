"""Reservations table. Parameterized queries only (SR-15).

Queries for one driver include "driver_id = ?" (SR-05).
"""
from .db import get_db


def insert(reservation_id, driver_id, vehicle_id, spot_id, start_time, end_time, created_at):
    get_db().execute(
        "INSERT INTO reservations"
        " (id, driver_id, vehicle_id, spot_id, start_time, end_time, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (reservation_id, driver_id, vehicle_id, spot_id, start_time, end_time, created_at),
    )


def count_overlapping(spot_id, start_time, end_time):
    """Reservations on this spot that overlap [start_time, end_time) (NFR-09).

    Two periods overlap when each one starts before the other ends. A booking
    that ends exactly when the next one starts does not overlap.
    """
    row = get_db().execute(
        "SELECT COUNT(*) AS n FROM reservations"
        " WHERE spot_id = ? AND start_time < ? AND end_time > ?",
        (spot_id, end_time, start_time),
    ).fetchone()
    return row["n"]


def list_for_driver(driver_id):
    return get_db().execute(
        "SELECT r.id, r.vehicle_id, r.start_time, r.end_time, s.label AS spot_label"
        " FROM reservations r JOIN spots s ON s.id = r.spot_id"
        " WHERE r.driver_id = ? ORDER BY r.start_time",
        (driver_id,),
    ).fetchall()


def get_for_driver(reservation_id, driver_id):
    return get_db().execute(
        "SELECT id, start_time FROM reservations WHERE id = ? AND driver_id = ?",
        (reservation_id, driver_id),
    ).fetchone()


def delete_for_driver(reservation_id, driver_id):
    get_db().execute(
        "DELETE FROM reservations WHERE id = ? AND driver_id = ?",
        (reservation_id, driver_id),
    )


def list_times_from(from_time):
    """Spot and times of current and future reservations, for the admin view.

    Only spot_id, start_time and end_time are selected: no driver ID, vehicle
    ID or reservation ID, so the admin never sees who booked a spot (SR-11).
    """
    return get_db().execute(
        "SELECT spot_id, start_time, end_time FROM reservations"
        " WHERE end_time > ? ORDER BY start_time",
        (from_time,),
    ).fetchall()
