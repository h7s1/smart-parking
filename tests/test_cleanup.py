"""Cleanup job: retention periods from the Personal Data Map (PR-07 to PR-10).

Old records are written straight into the database with old dates, then the
job is run, as the "Retention and cleanup" checks describe.
"""
import contextlib
import io
import sqlite3
import time
import unittest
import uuid
from datetime import timedelta

from helpers import ADMIN_EMAIL, AppTestCase

from app import cleanup


class CleanupTests(AppTestCase):

    def setUp(self):
        super().setUp()
        dana = self.new_driver("dana@test.example")
        self.vehicle = self.add_vehicle(dana, "ABC1234")
        self.driver_id = self.query("SELECT owner_id FROM vehicles")[0]["owner_id"]
        self.spot = self.spot_ids["A-01"]

    # ----- helpers -----

    def ago(self, **period):
        return (self.clock() - timedelta(**period)).strftime("%Y-%m-%d %H:%M:%S")

    def execute(self, sql, params=()):
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(sql, params)
            conn.commit()
        finally:
            conn.close()

    def add_session(self, entered_days_ago, exited=True):
        session_id = str(uuid.uuid4())
        entry = self.ago(days=entered_days_ago)
        self.execute("INSERT INTO parking_sessions (id, vehicle_id, spot_id, entry_time, exit_time)"
                     " VALUES (?, ?, ?, ?, ?)",
                     (session_id, self.vehicle, self.spot, entry,
                      self.ago(days=entered_days_ago, hours=-1) if exited else None))
        return session_id

    def add_reservation(self, ended_days_ago):
        reservation_id = str(uuid.uuid4())
        self.execute("INSERT INTO reservations"
                     " (id, driver_id, vehicle_id, spot_id, start_time, end_time, created_at)"
                     " VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (reservation_id, self.driver_id, self.vehicle, self.spot,
                      self.ago(days=ended_days_ago, hours=1), self.ago(days=ended_days_ago),
                      self.ago(days=ended_days_ago + 1)))
        return reservation_id

    def add_dispute(self, closed_days_ago=None, reservation_id=None, session_id=None):
        dispute_id = str(uuid.uuid4())
        status = "OPEN" if closed_days_ago is None else "CLOSED"
        closed = None if closed_days_ago is None else self.ago(days=closed_days_ago)
        self.execute("INSERT INTO disputes (id, driver_id, reservation_id, parking_session_id,"
                     " reason, status, created_at, closed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                     (dispute_id, self.driver_id, reservation_id, session_id,
                      "RESERVED_SPOT_TAKEN", status, self.ago(days=200), closed))
        return dispute_id

    def ids(self, table):
        return {row["id"] for row in self.query(f"SELECT id FROM {table}")}

    def run_cleanup(self):
        with self.app.app_context():
            return cleanup.run()

    # ----- PR-07 to PR-10 -----

    def test_parking_sessions_deleted_90_days_after_entry(self):
        """PR-07 (G1)"""
        old, recent = self.add_session(91), self.add_session(10)
        still_inside = self.add_session(91, exited=False)     # kept until the car leaves
        self.run_cleanup()
        self.assertEqual(self.ids("parking_sessions"), {recent, still_inside})
        self.assertNotIn(old, self.ids("parking_sessions"))

    def test_old_session_with_open_dispute_is_kept(self):
        """PR-07 (G2): kept while the dispute is open, deleted after it closes."""
        session_id = self.add_session(120)
        dispute_id = self.add_dispute(session_id=session_id)
        self.run_cleanup()
        self.assertEqual(self.ids("parking_sessions"), {session_id})
        self.execute("UPDATE disputes SET status = 'CLOSED', closed_at = ? WHERE id = ?",
                     (self.ago(days=1), dispute_id))
        self.run_cleanup()
        self.assertEqual(self.ids("parking_sessions"), set())

    def test_reservations_deleted_30_days_after_they_end(self):
        """PR-08 (G3)"""
        old, recent = self.add_reservation(31), self.add_reservation(29)
        disputed = self.add_reservation(60)
        self.add_dispute(reservation_id=disputed)
        self.run_cleanup()
        self.assertEqual(self.ids("reservations"), {recent, disputed})
        self.assertNotIn(old, self.ids("reservations"))

    def test_disputes_deleted_90_days_after_closing(self):
        """PR-09 (G4)"""
        reservation_id = self.add_reservation(1)
        old = self.add_dispute(closed_days_ago=91, reservation_id=reservation_id)
        recent = self.add_dispute(closed_days_ago=10, reservation_id=reservation_id)
        still_open = self.add_dispute(reservation_id=reservation_id)
        self.run_cleanup()
        self.assertEqual(self.ids("disputes"), {recent, still_open})
        self.assertNotIn(old, self.ids("disputes"))

    def test_audit_entries_deleted_after_180_days(self):
        """PR-10 (G5). The trigger still blocks deleting newer entries."""
        old, recent = str(uuid.uuid4()), str(uuid.uuid4())
        for entry_id, days in ((old, 365), (recent, 10)):
            self.execute("INSERT INTO audit_log (id, user_id, action, target_id, ip_address, created_at)"
                         " VALUES (?, NULL, 'LOGIN_FAILED', NULL, NULL, ?)", (entry_id, self.ago(days=days)))
        self.run_cleanup()
        self.assertNotIn(old, self.ids("audit_log"))
        self.assertIn(recent, self.ids("audit_log"))
        with self.assertRaises(sqlite3.IntegrityError):
            self.execute("DELETE FROM audit_log WHERE id = ?", (recent,))

    # ----- Data map: inactive accounts and expired login sessions -----

    def test_accounts_deleted_after_12_months_without_login(self):
        """Data map: email kept until the account is deleted or 12 months of inactivity."""
        self.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (self.ago(days=366), self.driver_id))
        omar = self.new_driver("omar@test.example")            # active: just logged in
        self.add_vehicle(omar, "XYZ9876")
        deleted = self.run_cleanup()
        self.assertEqual(deleted["inactive_accounts"], 1)
        self.assertNotIn(self.driver_id, self.ids("users"))
        self.assertEqual(len(self.query("SELECT id FROM vehicles")), 1)    # only Omar's car
        entry = self.query("SELECT user_id, target_id FROM audit_log"
                           " WHERE action = 'INACTIVE_ACCOUNT_DELETED'")
        self.assertEqual([(e["user_id"], e["target_id"]) for e in entry], [(None, self.driver_id)])
        self.login(ADMIN_EMAIL)                                  # staff who log in are kept

    def test_account_with_parked_car_is_kept(self):
        self.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (self.ago(days=400), self.driver_id))
        self.add_session(1, exited=False)
        self.run_cleanup()
        self.assertIn(self.driver_id, self.ids("users"))

    def test_expired_login_sessions_removed(self):
        """SR-05: sessions idle for more than 30 minutes are deleted from the table."""
        self.assertEqual(len(self.query("SELECT token_hash FROM login_sessions")), 1)
        self.clock.advance(minutes=31)
        self.login(ADMIN_EMAIL)
        self.run_cleanup()
        self.assertEqual(len(self.query("SELECT token_hash FROM login_sessions")), 1)

    # ----- Flow 9: runs on its own -----

    def test_job_runs_at_start_up_and_is_scheduled(self):
        """G6: start_daily() runs the job right away in a background thread."""
        old = self.add_session(91)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            stop = cleanup.start_daily(self.app)
            try:
                for _ in range(100):                 # wait up to 10 seconds for the first run
                    if "Cleanup job" in output.getvalue():
                        break
                    time.sleep(0.1)
            finally:
                stop.set()
        self.assertNotIn(old, self.ids("parking_sessions"))
        self.assertIn("Cleanup job: deleted", output.getvalue())


if __name__ == "__main__":
    unittest.main()
