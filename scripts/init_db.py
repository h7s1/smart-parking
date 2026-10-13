"""Create the database and fill it with synthetic data.

All data is invented for testing; no real personal data is used. All
passwords are random and printed once; they are not stored anywhere in the
code.

Run from the project folder:
    python scripts/init_db.py           # create a new database
    python scripts/init_db.py --reset   # delete the database and start again
"""
import secrets
import sys
import uuid
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import clock, create_app                            # noqa: E402
from app.data_access import reservations_repo, spots_repo    # noqa: E402
from app.data_access.db import create_schema, get_db         # noqa: E402
from app.logic import accounts, vehicles                     # noqa: E402

SPOTS = [f"A-{n:02d}" for n in range(1, 11)]
DISABLED_SPOT = "A-10"

# Two synthetic drivers, so one can try to reach the other's data.
DRIVERS = (("driver1@smartparking.test", "ABC1234"),
           ("driver2@smartparking.test", "XYZ9876"))

# driver1's car gets a reservation on A-01 that has already started, so the
# gate simulator can be tried right away (a driver can only book future times).
DEMO_RESERVATION_HOURS = 8


def new_password():
    return secrets.token_urlsafe(15)        # 20 characters


def main():
    try:
        app = create_app()
    except RuntimeError as error:
        print(error)
        return 1
    db_file = Path(app.config["DATABASE"])

    if db_file.exists():
        if "--reset" not in sys.argv:
            print(f"The database already exists: {db_file}")
            print("Use --reset to delete it and create a new one.")
            return 1
        db_file.unlink()
    db_file.parent.mkdir(parents=True, exist_ok=True)

    accounts_created = []
    with app.app_context():
        create_schema(get_db())

        spot_ids = {}
        for label in SPOTS:
            status = "DISABLED" if label == DISABLED_SPOT else "FREE"
            spot_ids[label] = str(uuid.uuid4())
            spots_repo.insert(spot_ids[label], label, status)

        for email, role in (("admin@smartparking.test", accounts.ADMIN),
                            ("support@smartparking.test", accounts.SUPPORT_AGENT)):
            password = new_password()
            accounts.create_staff_account(email, password, role)
            accounts_created.append((role, email, password))

        vehicle_ids = {}
        for email, plate in DRIVERS:
            password = new_password()
            driver_id = accounts.register_driver(email, password)
            vehicle_ids[email] = (driver_id, vehicles.add_vehicle(driver_id, plate)["id"])
            accounts_created.append((accounts.DRIVER, email, password))

        driver_id, vehicle_id = vehicle_ids[DRIVERS[0][0]]
        start = clock.now()
        reservations_repo.insert(
            str(uuid.uuid4()), driver_id, vehicle_id, spot_ids["A-01"],
            clock.to_db(start), clock.to_db(start + timedelta(hours=DEMO_RESERVATION_HOURS)),
            clock.to_db(start),
        )

    print(f"Database created: {db_file}")
    print(f"{len(SPOTS)} spots ({DISABLED_SPOT} is disabled).")
    print(f"Vehicles: {DRIVERS[0][1]} (driver1), {DRIVERS[1][1]} (driver2).")
    print(f"driver1 has a reservation on A-01 for the next {DEMO_RESERVATION_HOURS} hours, "
          "so you can try: python scripts/gate_simulator.py entry ABC1234")
    print("\nSynthetic accounts (shown only now, copy them somewhere safe):")
    for role, email, password in accounts_created:
        print(f"  {role:<14} {email:<28} {password}")
    print("\nNext: python run.py   then open https://localhost:5000")
    return 0


if __name__ == "__main__":
    sys.exit(main())
