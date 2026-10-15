"""Parking administration (FR-12, FR-13, FR-14)."""
from collections import defaultdict

from .. import clock
from ..data_access import audit_repo, reservations_repo, spots_repo
from ..errors import Conflict, NotFound, ValidationError

ADMIN_STATUSES = ("FREE", "DISABLED")
AUDIT_LOG_LIMIT = 200


def spot_overview():
    """FR-12: status and reserved times of every spot.

    Reserved times include only start and end, never the driver, vehicle or
    reservation, so the admin cannot see who will be where (SR-14).
    """
    times = defaultdict(list)
    for row in reservations_repo.list_times_from(clock.to_db(clock.now())):
        times[row["spot_id"]].append(
            {"start": clock.db_to_api(row["start_time"]), "end": clock.db_to_api(row["end_time"])}
        )
    return [
        {
            "id": spot["id"],
            "label": spot["label"],
            "status": spot["status"],
            "reserved_times": times[spot["id"]],
        }
        for spot in spots_repo.list_all()
    ]


def set_spot_status(spot_id, status):
    """FR-13: the admin can switch a spot between FREE and DISABLED only.
    OCCUPIED is set by the gate, not by the admin."""
    if status not in ADMIN_STATUSES:
        raise ValidationError("Status must be FREE or DISABLED.")
    spot = spots_repo.get(spot_id)
    if spot is None:
        raise NotFound()
    if spot["status"] not in ADMIN_STATUSES:
        raise Conflict("An occupied spot cannot be changed.")
    spots_repo.set_status(spot_id, status)
    return {"id": spot_id, "label": spot["label"], "status": status}


def read_audit_log():
    """FR-14, SR-12: the latest audit entries, read-only."""
    return [
        {
            "time": clock.db_to_api(row["created_at"]),
            "action": row["action"],
            "user_id": row["user_id"],
            "target_id": row["target_id"],
            "ip_address": row["ip_address"],
        }
        for row in audit_repo.list_recent(AUDIT_LOG_LIMIT)
    ]
