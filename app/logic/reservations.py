"""Parking reservations (FR-06, FR-07, NFR-09)."""
import uuid
from datetime import timedelta

from flask import current_app

from .. import clock, notification
from ..data_access import reservations_repo, spots_repo, vehicles_repo
from ..data_access.db import transaction
from ..errors import Conflict, NotFound, ValidationError


def list_free_spots():
    """Spots a driver can choose from. Shows no information about other drivers."""
    return [
        {"id": row["id"], "label": row["label"]}
        for row in spots_repo.list_with_status("FREE")
    ]


def create(driver_id, vehicle_id, spot_id, start, end):
    """FR-06: reserve a spot with status FREE for a start and end time."""
    max_hours = current_app.config["MAX_RESERVATION_HOURS"]
    if start <= clock.now():
        raise ValidationError("The start time must be in the future.")
    if end <= start:
        raise ValidationError("The end time must be after the start time.")
    if end - start > timedelta(hours=max_hours):
        raise ValidationError(f"A reservation can last at most {max_hours} hours.")

    start_db, end_db = clock.to_db(start), clock.to_db(end)
    reservation_id = str(uuid.uuid4())

    # The write lock is taken before checking for overlaps, so two drivers
    # cannot both pass the check and book the same time (NFR-09).
    with transaction(immediate=True):
        if vehicles_repo.get_for_owner(vehicle_id, driver_id) is None:
            raise NotFound()                       # not this driver's vehicle (SR-05)
        spot = spots_repo.get(spot_id)
        if spot is None:
            raise NotFound()
        if spot["status"] != "FREE":
            raise Conflict("This spot cannot be reserved right now.")
        if reservations_repo.count_overlapping(spot_id, start_db, end_db) > 0:
            raise Conflict("This spot is already reserved for part of that time.")
        reservations_repo.insert(
            reservation_id, driver_id, vehicle_id, spot_id, start_db, end_db,
            clock.to_db(clock.now()),
        )

    reservation = {
        "id": reservation_id,
        "spot": spot["label"],
        "vehicle_id": vehicle_id,
        "start": clock.db_to_api(start_db),
        "end": clock.db_to_api(end_db),
    }
    # FR-08, flow 10: the email is sent only after the reservation is saved.
    notification.send_reservation_confirmation(driver_id, reservation)
    return reservation


def list_for_driver(driver_id):
    return [
        {
            "id": row["id"],
            "spot": row["spot_label"],
            "vehicle_id": row["vehicle_id"],
            "start": clock.db_to_api(row["start_time"]),
            "end": clock.db_to_api(row["end_time"]),
        }
        for row in reservations_repo.list_for_driver(driver_id)
    ]


def cancel(driver_id, reservation_id):
    """FR-07: a driver can cancel their own reservation up to 30 minutes before it starts."""
    row = reservations_repo.get_for_driver(reservation_id, driver_id)
    if row is None:
        raise NotFound()                           # not this driver's reservation (SR-05)
    minutes = current_app.config["CANCEL_DEADLINE_MINUTES"]
    if clock.from_db(row["start_time"]) - clock.now() < timedelta(minutes=minutes):
        raise Conflict(
            f"A reservation can only be cancelled up to {minutes} minutes before it starts."
        )
    reservations_repo.delete_for_driver(reservation_id, driver_id)
