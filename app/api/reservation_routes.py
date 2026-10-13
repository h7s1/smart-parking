"""Spot, reservation and parking history routes (drivers only)."""
from flask import g, jsonify

from . import bp, validation
from .guards import roles_required
from ..logic import gate, reservations
from ..logic.accounts import DRIVER


@bp.get("/spots")
@roles_required(DRIVER)
def free_spots():
    return jsonify(spots=reservations.list_free_spots())


@bp.get("/reservations")
@roles_required(DRIVER)
def list_reservations():
    return jsonify(reservations=reservations.list_for_driver(g.user["id"]))


@bp.post("/reservations")
@roles_required(DRIVER)
def create_reservation():
    """FR-06, NFR-03 (confirmation message), NFR-09."""
    data = validation.json_body()
    reservation = reservations.create(
        driver_id=g.user["id"],
        vehicle_id=validation.body_id(data, "vehicle_id", "Vehicle"),
        spot_id=validation.body_id(data, "spot_id", "Spot"),
        start=validation.time(data, "start", "Start time"),
        end=validation.time(data, "end", "End time"),
    )
    return jsonify(message="Reservation confirmed.", reservation=reservation), 201


@bp.delete("/reservations/<reservation_id>")
@roles_required(DRIVER)
def cancel_reservation(reservation_id):
    """FR-07, NFR-03."""
    reservations.cancel(g.user["id"], validation.path_id(reservation_id))
    return jsonify(message="Reservation cancelled.")


@bp.get("/parking-history")
@roles_required(DRIVER)
def parking_history():
    """The driver's own parking sessions. Read only: no route changes them (SR-12)."""
    return jsonify(parking_sessions=gate.history_for_driver(g.user["id"]))
