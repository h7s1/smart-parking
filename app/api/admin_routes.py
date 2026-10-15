"""Admin routes (admins only)."""
from flask import jsonify

from . import bp, validation
from .guards import roles_required
from ..logic import admin
from ..logic.accounts import ADMIN


@bp.get("/admin/spots")
@roles_required(ADMIN)
def spot_overview():
    """FR-12, SR-14."""
    return jsonify(spots=admin.spot_overview())


@bp.patch("/admin/spots/<spot_id>")
@roles_required(ADMIN)
def set_spot_status(spot_id):
    """FR-13."""
    data = validation.json_body()
    status = validation.choice(data, "status", "Status", admin.ADMIN_STATUSES)
    spot = admin.set_spot_status(validation.path_id(spot_id), status)
    return jsonify(message="Spot updated.", spot=spot)


@bp.get("/admin/audit-log")
@roles_required(ADMIN)
def audit_log():
    """FR-14, SR-12: only admins can read the audit log."""
    return jsonify(entries=admin.read_audit_log())
