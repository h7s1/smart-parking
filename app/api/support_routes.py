"""Support agent routes (FR-16, FR-17, SR-09, NFR-08). Support agents only."""
from flask import g, jsonify

from . import bp, validation
from .guards import roles_required
from ..logic import disputes
from ..logic.accounts import SUPPORT_AGENT


@bp.get("/support/disputes")
@roles_required(SUPPORT_AGENT)
def open_disputes():
    """FR-16: all open disputes."""
    return jsonify(disputes=disputes.list_open())


@bp.post("/support/disputes/<dispute_id>/close")
@roles_required(SUPPORT_AGENT)
def close_dispute(dispute_id):
    """FR-17."""
    validation.json_body()                    # changes are sent as JSON
    disputes.close_dispute(g.user["id"], validation.path_id(dispute_id))
    return jsonify(message="Dispute closed.")


@bp.get("/support/drivers/<driver_id>")
@roles_required(SUPPORT_AGENT)
def driver_data(driver_id):
    """SR-09: only while the driver has an open dispute. Every attempt is
    recorded in the audit log, including refused ones (NFR-08)."""
    return jsonify(disputes.driver_data_for_support(g.user["id"], validation.path_id(driver_id)))
