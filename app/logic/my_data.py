"""Download my data (P-02, fixed in Week 12).

The PDPL gives a driver the right to get a copy of their personal data. A
driver can download everything the system keeps about them as one JSON file.
Internal IDs are left out, because the Personal Data Map says user IDs are not
shown to drivers; plates are shown instead of vehicle IDs.
"""
from .. import clock
from ..data_access import (disputes_repo, parking_sessions_repo, reservations_repo,
                           users_repo, vehicles_repo)
from ..errors import ValidationError
from ..security import audit, crypto, passwords

AUDIT_NOTE = ("Security records (your user ID, your actions and your IP address) are kept "
              "for 180 days to investigate misuse, and are not part of this download.")


def export_driver_data(user_id, password):
    """The password is asked again, like for account deletion, so someone who
    finds an open session on a shared computer cannot download the data."""
    user = users_repo.get(user_id)
    if user is None or not passwords.verify_password(password, user["password_hash"]):
        raise ValidationError("The password is not correct.")

    account = users_repo.get_account_details(user_id)
    plates = {
        row["id"]: crypto.decrypt(row["plate_enc"], crypto.PLATE)
        for row in vehicles_repo.list_for_owner(user_id)
    }
    data = {
        "exported_at": clock.db_to_api(clock.to_db(clock.now())),
        "account": {
            "email": crypto.decrypt(account["email_enc"], crypto.EMAIL),
            "role": account["role"],
            "created": clock.db_to_api(account["created_at"]),
            "last_login": clock.db_to_api(account["last_login_at"]),
        },
        "vehicles": [
            {"plate": plates[row["id"]], "added": clock.db_to_api(row["created_at"])}
            for row in vehicles_repo.list_for_owner(user_id)
        ],
        "reservations": [
            {"bay": row["spot_label"], "plate": plates.get(row["vehicle_id"]),
             "start": clock.db_to_api(row["start_time"]), "end": clock.db_to_api(row["end_time"])}
            for row in reservations_repo.list_for_driver(user_id)
        ],
        "parking_history": [
            {"bay": row["spot_label"], "plate": plates.get(row["vehicle_id"]),
             "entry": clock.db_to_api(row["entry_time"]), "exit": clock.db_to_api(row["exit_time"])}
            for row in parking_sessions_repo.list_for_owner(user_id)
        ],
        "disputes": [
            {"about": "RESERVATION" if row["reservation_id"] else "PARKING_SESSION",
             "reason": row["reason"], "status": row["status"],
             "opened": clock.db_to_api(row["created_at"]), "closed": clock.db_to_api(row["closed_at"])}
            for row in disputes_repo.list_for_driver(user_id)
        ],
        "note": AUDIT_NOTE,
    }
    audit.record(audit.DATA_EXPORTED, user_id=user_id, target_id=user_id)
    return data
