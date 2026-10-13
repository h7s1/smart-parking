"""Vehicles (FR-04, FR-05). Plates are stored encrypted (PR-04)."""
import uuid

from .. import clock
from ..data_access import parking_sessions_repo, vehicles_repo
from ..data_access.db import transaction
from ..errors import Conflict, NotFound
from ..security import crypto


def add_vehicle(owner_id, plate):
    """FR-04: the plate must not belong to any registered vehicle."""
    vehicle_id = str(uuid.uuid4())
    with transaction(immediate=True):
        for row in vehicles_repo.list_plate_ciphertexts():
            if crypto.decrypt(row["plate_enc"], crypto.PLATE) == plate:
                # Does not say who owns the plate (SR-16).
                raise Conflict("This license plate cannot be added.")
        vehicles_repo.insert(
            vehicle_id, owner_id, crypto.encrypt(plate, crypto.PLATE), clock.to_db(clock.now())
        )
    return {"id": vehicle_id, "plate": plate}


def list_vehicles(owner_id):
    return [
        {"id": row["id"], "plate": crypto.decrypt(row["plate_enc"], crypto.PLATE)}
        for row in vehicles_repo.list_for_owner(owner_id)
    ]


def remove_vehicle(owner_id, vehicle_id):
    """FR-05. If the vehicle is not this driver's, the answer is "Not found",
    exactly as if it did not exist (SR-05). A car that is parked right now
    cannot be removed, so its spot is not left OCCUPIED."""
    with transaction(immediate=True):
        if vehicles_repo.get_for_owner(vehicle_id, owner_id) is None:
            raise NotFound()
        if parking_sessions_repo.get_open_for_vehicle(vehicle_id) is not None:
            raise Conflict("A vehicle that is parked cannot be removed. Remove it after it leaves.")
        vehicles_repo.delete_for_owner(vehicle_id, owner_id)
