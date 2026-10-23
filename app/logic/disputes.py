"""Disputes and support agent access (FR-15, FR-16, FR-17, SR-09, NFR-08).

A driver opens a dispute about one of their own reservations or parking
sessions, choosing a reason from a fixed list. While the dispute is open, a
support agent can see only the record it is about and the plate of that
record's vehicle (SR-09), not the rest of the driver's reservations, visits or
cars (data minimization). Every attempt by a support agent to see a disputed
record is recorded in the audit log, including refused attempts (NFR-08).
"""
import uuid

from .. import clock
from ..data_access import disputes_repo, parking_sessions_repo, reservations_repo, vehicles_repo
from ..data_access.db import transaction
from ..errors import Conflict, Forbidden, NotFound
from ..security import audit, crypto

# The fixed list of reasons (FR-15). Same list as the CHECK in schema.sql.
REASONS = (
    "GATE_DENIED_WITH_RESERVATION",
    "WRONG_ENTRY_OR_EXIT_TIME",
    "RESERVED_SPOT_TAKEN",
    "RESERVATION_NOT_SHOWN",
)

NO_OPEN_DISPUTE = "You can see a record only while its dispute is open."


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
            raise NotFound()                       # not this driver's record (SR-08)
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
    """FR-17. Closing ends the support agent's access to the disputed record."""
    with transaction(immediate=True):
        status = disputes_repo.get_status(dispute_id)
        if status is None:
            raise NotFound()
        if status != "OPEN":
            raise Conflict("This dispute is already closed.")
        disputes_repo.close(dispute_id, clock.to_db(clock.now()))
        audit.record(audit.DISPUTE_CLOSED, user_id=agent_id, target_id=dispute_id)


def disputed_record_for_support(agent_id, dispute_id):
    """SR-09, NFR-08: the one reservation or parking session that an open
    dispute is about, and the plate of its vehicle. Nothing else about the
    driver is sent: no other reservations, visits or cars, and never the
    email or password hash.

    The attempt is recorded before the answer is sent, whether it is allowed
    or refused. A closed dispute and a dispute ID that does not exist get the
    same refusal, so IDs cannot be tested.
    """
    dispute = disputes_repo.get(dispute_id)
    allowed = dispute is not None and dispute["status"] == "OPEN"
    audit.record(audit.SUPPORT_ACCESS if allowed else audit.SUPPORT_ACCESS_DENIED,
                 user_id=agent_id, target_id=dispute_id)
    if not allowed:
        raise Forbidden(NO_OPEN_DISPUTE)

    if dispute["reservation_id"] is not None:
        row = reservations_repo.get_with_spot(dispute["reservation_id"])
        about = "RESERVATION"
        record = {"id": row["id"], "spot": row["spot_label"],
                  "start": clock.db_to_api(row["start_time"]),
                  "end": clock.db_to_api(row["end_time"])}
    else:
        row = parking_sessions_repo.get_with_spot(dispute["parking_session_id"])
        about = "PARKING_SESSION"
        record = {"id": row["id"], "spot": row["spot_label"],
                  "entry": clock.db_to_api(row["entry_time"]),
                  "exit": clock.db_to_api(row["exit_time"])}
    plate = crypto.decrypt(vehicles_repo.get_plate_ciphertext(row["vehicle_id"]), crypto.PLATE)
    return {"dispute_id": dispute_id, "about": about, "record": record, "plate": plate}
