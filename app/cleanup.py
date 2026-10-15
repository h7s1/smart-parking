"""Cleanup job (Figure 1, flow 9): deletes records whose retention period has ended.

  PR-07  parking sessions 90 days after entry, unless linked to an open dispute
  PR-08  reservations 30 days after they end, unless linked to an open dispute
  PR-09  disputes 90 days after they are closed
  PR-10  audit log entries 180 days after they are created
  Data map: accounts after 12 months without a login, and login sessions that
  have expired (SR-05)

Deleting a reservation or parking session also deletes the closed disputes
about it (ON DELETE CASCADE in schema.sql).

run.py starts the job when the server starts and then once a day. It can also
be run by hand:  python scripts/run_cleanup.py
"""
import threading
from datetime import timedelta

from flask import current_app

from . import clock
from .data_access import (audit_repo, disputes_repo, parking_sessions_repo, reservations_repo,
                          sessions_repo, users_repo)
from .data_access.db import transaction
from .security import audit


def run():
    """Delete everything that has passed its retention period. Returns the
    number of deleted records of each kind. All or nothing: one transaction."""
    config = current_app.config
    now = clock.now()

    def before(**period):
        return clock.to_db(now - timedelta(**period))

    deleted = {}
    with transaction(immediate=True):
        deleted["disputes"] = disputes_repo.delete_expired(
            before(days=config["DISPUTE_RETENTION_DAYS"]))
        deleted["parking_sessions"] = parking_sessions_repo.delete_expired(
            before(days=config["PARKING_SESSION_RETENTION_DAYS"]))
        deleted["reservations"] = reservations_repo.delete_expired(
            before(days=config["RESERVATION_RETENTION_DAYS"]))
        deleted["audit_entries"] = audit_repo.delete_expired(
            before(days=config["AUDIT_RETENTION_DAYS"]), config["AUDIT_RETENTION_DAYS"])

        inactive = users_repo.list_inactive(before(days=config["INACTIVE_ACCOUNT_DAYS"]))
        for row in inactive:
            users_repo.delete(row["id"])           # cascades like a normal account deletion (PR-11)
            audit.record(audit.INACTIVE_ACCOUNT_DELETED, target_id=row["id"])
        deleted["inactive_accounts"] = len(inactive)

        deleted["login_sessions"] = sessions_repo.delete_idle(
            before(minutes=config["SESSION_IDLE_MINUTES"]))
    return deleted


def summary(deleted):
    return "Cleanup job: deleted " + ", ".join(f"{n} {kind.replace('_', ' ')}"
                                               for kind, n in deleted.items()) + "."


def start_daily(app):
    """Run the job now, then every CLEANUP_INTERVAL_HOURS, in a background
    thread. Returns an Event; set it to stop the job."""
    stop = threading.Event()
    interval = app.config["CLEANUP_INTERVAL_HOURS"] * 3600

    def loop():
        while True:
            try:
                with app.app_context():
                    print(summary(run()), flush=True)
            except Exception:                    # noqa: BLE001 - keep the job alive
                app.logger.exception("The cleanup job failed; it will try again next time.")
            if stop.wait(interval):
                return

    threading.Thread(target=loop, name="cleanup-job", daemon=True).start()
    return stop
