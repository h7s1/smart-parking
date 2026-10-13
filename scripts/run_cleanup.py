"""Run the cleanup job once, by hand (PR-07 to PR-10).

The server already runs it when it starts and then once a day. Use this to
test the retention rules: add old records in DB Browser, then run:
    python scripts/run_cleanup.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import cleanup, create_app                    # noqa: E402
from app.data_access.db import check_database_file     # noqa: E402


def main():
    try:
        app = create_app()
        check_database_file(app.config["DATABASE"])
    except RuntimeError as error:
        print(error)
        return 1
    with app.app_context():
        print(cleanup.summary(cleanup.run()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
