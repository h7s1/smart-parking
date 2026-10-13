"""Dispute routes for drivers (FR-15)."""
from flask import g, jsonify

from . import bp, validation
from .guards import roles_required
from ..logic import disputes
from ..logic.accounts import DRIVER


@bp.get("/disputes")
@roles_required(DRIVER)
def list_my_disputes():
    return jsonify(disputes=disputes.list_for_driver(g.user["id"]))


@bp.post("/disputes")
@roles_required(DRIVER)
def open_dispute():
    """FR-15: about one of the driver's own reservations or parking sessions,
    with a reason from the fixed list."""
    data = validation.json_body()
    reason = validation.choice(data, "reason", "Reason", disputes.REASONS)
    reservation_id, parking_session_id = validation.dispute_subject(data)
    dispute = disputes.open_dispute(g.user["id"], reason, reservation_id, parking_session_id)
    return jsonify(message="Dispute opened. A support agent will look into it.", dispute=dispute), 201
