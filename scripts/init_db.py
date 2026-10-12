"""Create the database and fill it with synthetic data.

All data is invented for testing; no real personal data is used. Staff
passwords are random and printed once; they are not stored anywhere in the
code.

Run from the project folder:
    python scripts/init_db.py           # create a new database
    python scripts/init_db.py --reset   # delete the database and start again
"""
import secrets
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app                                   # noqa: E402
from app.data_access import spots_repo                       # noqa: E402
from app.data_access.db import create_schema, get_db         # noqa: E402
from app.logic import accounts, vehicles                     # noqa: E402

SPOTS = [f"A-{n:02d}" for n in range(1, 11)]
DISABLED_SPOT = "A-10"


def new_password():
    return secrets.token_urlsafe(15)        # 20 characters


def main():
    app = create_app()
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

        for label in SPOTS:
            status = "DISABLED" if label == DISABLED_SPOT else "FREE"
            spots_repo.insert(str(uuid.uuid4()), label, status)

        for email, role in (("admin@smartparking.test", accounts.ADMIN),
                            ("support@smartparking.test", accounts.SUPPORT_AGENT)):
            password = new_password()
            accounts.create_staff_account(email, password, role)
            accounts_created.append((role, email, password))

        password = new_password()
        driver_id = accounts.register_driver("driver1@smartparking.test", password)
        vehicles.add_vehicle(driver_id, "ABC1234")
        accounts_created.append((accounts.DRIVER, "driver1@smartparking.test", password))

    print(f"Database created: {db_file}")
    print(f"{len(SPOTS)} spots ({DISABLED_SPOT} is disabled).")
    print("\nSynthetic accounts (shown only now, copy them somewhere safe):")
    for role, email, password in accounts_created:
        print(f"  {role:<14} {email:<28} {password}")
    print("\nNext: python run.py   then open https://localhost:5000")
    return 0


if __name__ == "__main__":
    sys.exit(main())
