"""Disputes and support agent access (FR-15, FR-16, FR-17, SR-06, NFR-08).

A driver opens a dispute about one of their own reservations or parking
sessions, choosing a reason from a fixed list. While the driver has an open
dispute, a support agent can see the driver's reservations, parking sessions
and plates (SR-06). Every attempt by a support agent to see a driver's data is
recorded in the audit log, including refused attempts (NFR-08).
"""
import uuid

from .. import clock
from ..data_access import disputes_repo, parking_sessions_repo, reservations_repo
from ..data_access.db import transaction
from ..errors import Conflict, Forbidden, NotFound
from ..security import audit
from . import gate, reservations, vehicles

# The fixed list of reasons (FR-15). Same list as the CHECK in schema.sql.
REASONS = (
    "GATE_DENIED_WITH_RESERVATION",
    "WRONG_ENTRY_OR_EXIT_TIME",
    "RESERVED_SPOT_TAKEN",
    "RESERVATION_NOT_SHOWN",
)

NO_OPEN_DISPUTE = "You can see a driver's data only while the driver has an open dispute."


def _as_dict(row):
    about_reservation = row["reservation_id"] is not None
    return {
        "id": row["id"],
        "driver_id": row["driver_id"],
        "about": "RESERVATION" if about_reservation else "PARKING_SESSION",
        "record_id": row["reservation_id"] if about_reservation else row["parking_session_id"],
        "reason": row["reason"],
        "status": row["status"],
        "opened": clock.db_to_api(row["created_at"]),
        "closed": clock.db_to_api(row["closed_at"]),
    }


def open_dispute(driver_id, reason, reservation_id=None, parking_session_id=None):
    """FR-15. Exactly one of reservation_id and parking_session_id is given
    (checked in api/validation.py)."""
    dispute_id = str(uuid.uuid4())
    with transaction(immediate=True):
        if reservation_id is not None:
            own = reservations_repo.get_for_driver(reservation_id, driver_id)
        else:
            own = parking_sessions_repo.get_for_owner(parking_session_id, driver_id)
        if own is None:
            raise NotFound()                       # not this driver's record (SR-05)
        if disputes_repo.has_open_for_record(reservation_id, parking_session_id):
            raise Conflict("There is already an open dispute about this.")
        disputes_repo.insert(dispute_id, driver_id, reservation_id, parking_session_id,
                             reason, clock.to_db(clock.now()))
        audit.record(audit.DISPUTE_OPENED, user_id=driver_id, target_id=dispute_id)
    return {"id": dispute_id, "status": "OPEN"}


def list_for_driver(driver_id):
    return [_as_dict(row) for row in disputes_repo.list_for_driver(driver_id)]


def list_open():
    """FR-16: all open disputes, for support agents."""
    return [_as_dict(row) for row in disputes_repo.list_open()]


def close_dispute(agent_id, dispute_id):
    """FR-17. Closing ends the support agent's access to the driver's data."""
    with transaction(immediate=True):
        status = disputes_repo.get_status(dispute_id)
        if status is None:
            raise NotFound()
        if status != "OPEN":
            raise Conflict("This dispute is already closed.")
        disputes_repo.close(dispute_id, clock.to_db(clock.now()))
        audit.record(audit.DISPUTE_CLOSED, user_id=agent_id, target_id=dispute_id)


def driver_data_for_support(agent_id, driver_id):
    """SR-06, NFR-08: a driver's reservations, parking sessions and plates.

    Allowed only while the driver has an open dispute. The attempt is recorded
    before the answer is sent, whether it is allowed or refused. A driver ID
    that does not exist gets the same refusal, so IDs cannot be tested.
    The driver's email and password hash are never part of the answer.
    """
    allowed = disputes_repo.driver_has_open(driver_id)
    audit.record(audit.SUPPORT_ACCESS if allowed else audit.SUPPORT_ACCESS_DENIED,
                 user_id=agent_id, target_id=driver_id)
    if not allowed:
        raise Forbidden(NO_OPEN_DISPUTE)
    return {
        "driver_id": driver_id,
        "vehicles": vehicles.list_vehicles(driver_id),
        "reservations": reservations.list_for_driver(driver_id),
        "parking_sessions": gate.history_for_driver(driver_id),
    }
