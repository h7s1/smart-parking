"""Vehicle routes (drivers only)."""
from flask import g, jsonify

from . import bp, validation
from .guards import roles_required
from ..logic import vehicles
from ..logic.accounts import DRIVER


@bp.get("/vehicles")
@roles_required(DRIVER)
def list_vehicles():
    # The owner is always the logged-in driver, taken from the session (SR-05).
    return jsonify(vehicles=vehicles.list_vehicles(g.user["id"]))


@bp.post("/vehicles")
@roles_required(DRIVER)
def add_vehicle():
    """FR-04."""
    plate = validation.plate(validation.json_body())
    vehicle = vehicles.add_vehicle(g.user["id"], plate)
    return jsonify(message="Vehicle added.", vehicle=vehicle), 201


@bp.delete("/vehicles/<vehicle_id>")
@roles_required(DRIVER)
def remove_vehicle(vehicle_id):
    """FR-05."""
    vehicles.remove_vehicle(g.user["id"], validation.path_id(vehicle_id))
    return jsonify(message="Vehicle removed.")
