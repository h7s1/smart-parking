"""Gate decision and parking history (FR-09, FR-10, FR-11, PR-01, PR-05, NFR-02).

The gate simulator sends a license plate and a direction (ENTRY or EXIT). The
plate is used only to find the vehicle, and then it is discarded (PR-01): it
is never stored, written to a log, or sent back. From that point on only the
vehicle ID is used, and parking sessions hold the vehicle ID only (PR-05).
"""
import uuid

from .. import clock
from ..data_access import parking_sessions_repo, reservations_repo, spots_repo, vehicles_repo
from ..data_access.db import transaction
from ..security import crypto

ALLOW = "ALLOW"
DENY = "DENY"
ENTRY = "ENTRY"
EXIT = "EXIT"
DIRECTIONS = (ENTRY, EXIT)


def _find_vehicle_id(plate):
    """Decrypt each stored plate and compare (team design, as in FR-04)."""
    for row in vehicles_repo.list_plate_ciphertexts():
        if crypto.decrypt(row["plate_enc"], crypto.PLATE) == plate:
            return row["id"]
    return None


def decide(plate, direction):
    """Return ALLOW or DENY for one gate event.

    Everything runs in one transaction with the write lock taken first, so two
    events at the same moment cannot both take the same spot.
    """
    now = clock.to_db(clock.now())
    with transaction(immediate=True):
        vehicle_id = _find_vehicle_id(plate)
        del plate                                   # PR-01: the plate cannot be used after this line
        if vehicle_id is None:
            return DENY                             # unregistered plate
        if direction == ENTRY:
            return _entry(vehicle_id, now)
        return _exit(vehicle_id, now)


def _entry(vehicle_id, now):
    """FR-09, FR-10: let the car in only if it has a reservation covering now."""
    if parking_sessions_repo.get_open_for_vehicle(vehicle_id) is not None:
        return DENY                                 # this car is already inside
    reservation = reservations_repo.find_covering(vehicle_id, now)
    if reservation is None:
        return DENY                                 # no reservation, or not for now
    spot = spots_repo.get(reservation["spot_id"])
    if spot["status"] != "FREE":
        return DENY                                 # spot disabled, or another car is still in it
    parking_sessions_repo.insert(str(uuid.uuid4()), vehicle_id, spot["id"], now)
    spots_repo.set_status(spot["id"], "OCCUPIED")   # shown to the admin (FR-12)
    return ALLOW


def _exit(vehicle_id, now):
    """FR-11: add the exit time to the car's open session and free the spot."""
    session = parking_sessions_repo.get_open_for_vehicle(vehicle_id)
    if session is None:
        return DENY                                 # no entry was recorded for this car
    parking_sessions_repo.close(session["id"], now)
    spots_repo.set_status(session["spot_id"], "FREE")
    return ALLOW


def history_for_driver(driver_id):
    """The driver's own parking history, read only (SR-08, SR-15)."""
    return [
        {
            "id": row["id"],
            "spot": row["spot_label"],
            "vehicle_id": row["vehicle_id"],
            "entry": clock.db_to_api(row["entry_time"]),
            "exit": clock.db_to_api(row["exit_time"]),
        }
        for row in parking_sessions_repo.list_for_owner(driver_id)
    ]
