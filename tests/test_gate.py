"""Gate simulator and gate decision (FR-09, FR-10, FR-11, SR-20, PR-01, PR-05, NFR-02).

The fake clock starts at 08:00. The driver's reservation on A-01 runs from
10:00 to 11:00, so start_reservation() moves the clock to 10:05.
"""
import time
import unittest

from helpers import ADMIN_EMAIL, GATE_KEY, PASSWORD, AppTestCase


class GateTests(AppTestCase):

    def setUp(self):
        super().setUp()
        self.dana = self.new_driver("dana@test.example")
        self.vehicle = self.add_vehicle(self.dana, "ABC1234")
        self.omar = self.new_driver("omar@test.example")
        self.omar_vehicle = self.add_vehicle(self.omar, "XYZ9876")
        self.assertEqual(self.reserve(self.dana, self.vehicle).status_code, 201)

    def start_reservation(self):
        self.clock.advance(hours=2, minutes=5)

    def spot_status(self, label="A-01"):
        return self.query("SELECT status FROM spots WHERE label = ?", (label,))[0]["status"]

    def sessions(self):
        return self.query("SELECT * FROM parking_sessions")

    # ----- FR-09 to FR-11 -----

    def test_entry_with_reservation_is_allowed(self):
        """FR-09, FR-10, FR-12: ALLOW, a new session, and the spot shows OCCUPIED."""
        self.start_reservation()
        self.assertEqual(self.decision("ABC1234"), "ALLOW")
        rows = self.sessions()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["vehicle_id"], self.vehicle)
        self.assertEqual(rows[0]["entry_time"], "2026-10-20 10:05:00")
        self.assertIsNone(rows[0]["exit_time"])
        self.assertEqual(self.spot_status(), "OCCUPIED")

    def test_exit_adds_exit_time_and_frees_the_spot(self):
        """FR-11"""
        self.start_reservation()
        self.decision("ABC1234")
        self.clock.advance(minutes=40)
        self.assertEqual(self.decision("ABC1234", "EXIT"), "ALLOW")
        self.assertEqual(self.sessions()[0]["exit_time"], "2026-10-20 10:45:00")
        self.assertEqual(self.spot_status(), "FREE")

    def test_plate_written_differently_still_matches(self):
        self.start_reservation()
        self.assertEqual(self.decision("abc-1234"), "ALLOW")

    def test_no_reservation_or_unregistered_plate_is_denied(self):
        """FR-09 (negative)"""
        self.start_reservation()
        self.assertEqual(self.decision("XYZ9876"), "DENY")     # registered, no reservation
        self.assertEqual(self.decision("NOPE123"), "DENY")     # not registered
        self.assertEqual(self.sessions(), [])

    def test_reservation_that_does_not_cover_now_is_denied(self):
        """FR-09 (negative): before the start, and after the end."""
        self.assertEqual(self.decision("ABC1234"), "DENY")
        self.clock.advance(hours=3, minutes=1)
        self.assertEqual(self.decision("ABC1234"), "DENY")
        self.assertEqual(self.sessions(), [])

    def test_cancelled_reservation_is_denied(self):
        """FR-09 (negative)"""
        reservation_id = self.dana.get("/api/reservations").get_json()["reservations"][0]["id"]
        self.assertEqual(self.dana.delete(f"/api/reservations/{reservation_id}").status_code, 200)
        self.start_reservation()
        self.assertEqual(self.decision("ABC1234"), "DENY")

    def test_same_car_cannot_enter_twice(self):
        self.start_reservation()
        self.assertEqual(self.decision("ABC1234"), "ALLOW")
        self.assertEqual(self.decision("ABC1234"), "DENY")
        self.assertEqual(len(self.sessions()), 1)

    def test_exit_without_entry_is_denied(self):
        self.assertEqual(self.decision("ABC1234", "EXIT"), "DENY")
        self.assertEqual(self.sessions(), [])

    def test_disabled_spot_is_denied(self):
        admin = self.login(ADMIN_EMAIL)
        admin.patch(f"/api/admin/spots/{self.spot_ids['A-01']}", json={"status": "DISABLED"})
        self.start_reservation()
        self.assertEqual(self.decision("ABC1234"), "DENY")

    def test_spot_still_taken_by_previous_car_is_denied(self):
        """Dana stays after her reservation ends; Omar's reservation on the same
        spot starts, but the spot is still OCCUPIED, so Omar is denied."""
        omar_start = self.reserve(self.omar, self.omar_vehicle, start_in_hours=3)
        self.assertEqual(omar_start.status_code, 201)
        self.start_reservation()
        self.assertEqual(self.decision("ABC1234"), "ALLOW")
        self.clock.advance(hours=1)                          # 11:05, Omar's time
        self.assertEqual(self.decision("XYZ9876"), "DENY")
        self.assertEqual(self.decision("ABC1234", "EXIT"), "ALLOW")
        self.assertEqual(self.decision("XYZ9876"), "ALLOW")

    def test_parked_car_cannot_be_removed_and_account_cannot_be_deleted(self):
        """The spot must not be left OCCUPIED with no session behind it."""
        self.start_reservation()
        self.decision("ABC1234")
        dana = self.login("dana@test.example")
        self.assertEqual(dana.delete(f"/api/vehicles/{self.vehicle}").status_code, 409)
        self.assertEqual(dana.post("/api/account/delete", json={"password": PASSWORD}).status_code, 409)
        self.assertEqual(self.spot_status(), "OCCUPIED")
        self.decision("ABC1234", "EXIT")
        self.assertEqual(dana.delete(f"/api/vehicles/{self.vehicle}").status_code, 200)

    def test_admin_cannot_change_an_occupied_spot(self):
        """FR-13: OCCUPIED is set by the gate only (checklist D5)."""
        self.start_reservation()
        self.decision("ABC1234")
        admin = self.login(ADMIN_EMAIL)
        for status in ("FREE", "DISABLED"):
            response = admin.patch(f"/api/admin/spots/{self.spot_ids['A-01']}", json={"status": status})
            self.assertEqual(response.status_code, 409)
        self.assertEqual(self.spot_status(), "OCCUPIED")

    # ----- SR-20, SR-17 -----

    def test_missing_or_wrong_gate_key_is_refused(self):
        """SR-20, TH-01 (negative): a fake gate cannot create entries."""
        self.start_reservation()
        for key in (None, "", "wrong-key", GATE_KEY[:-1], GATE_KEY + "x"):
            with self.assertLogs(self.app.logger, level="WARNING"):   # refusals are logged
                response = self.gate("ABC1234", key=key)
            self.assertEqual(response.status_code, 401, key)
            self.assertNotIn("decision", response.get_json())
        self.assertEqual(self.sessions(), [])
        self.assertEqual(self.spot_status(), "FREE")

    def test_invalid_gate_input_is_rejected(self):
        """SR-17 (negative): nothing is stored."""
        self.start_reservation()
        for body in ({"plate": "ABC1234", "direction": "SIDEWAYS"},
                     {"plate": "' OR 1=1 --", "direction": "ENTRY"},
                     {"plate": "A" * 500, "direction": "ENTRY"},
                     {"plate": 1234, "direction": "ENTRY"},
                     {"direction": "ENTRY"}):
            response = self.client().post("/api/gate/events", json=body,
                                          headers={"X-Gate-Key": GATE_KEY})
            self.assertEqual(response.status_code, 400, body)
        self.assertEqual(self.sessions(), [])

    # ----- PR-01, PR-05, NFR-02 -----

    def test_plate_is_discarded_after_the_decision(self):
        """PR-01, PR-05: the plate is not sent back, stored or logged."""
        self.start_reservation()
        with self.assertNoLogs(self.app.logger):
            response = self.gate("ABC1234")
        self.assertEqual(response.get_json(), {"decision": "ALLOW"})
        columns = [row["name"] for row in self.query("PRAGMA table_info(parking_sessions)")]
        self.assertEqual(columns, ["id", "vehicle_id", "spot_id", "entry_time", "exit_time"])
        with open(self.db_path, "rb") as db_file:
            self.assertNotIn(b"ABC1234", db_file.read())

    def test_decision_takes_less_than_2_seconds(self):
        """NFR-02, measured with 50 registered vehicles."""
        for n in range(48):
            self.add_vehicle(self.omar, f"TST{n:04d}")
        self.start_reservation()
        started = time.perf_counter()
        self.assertEqual(self.decision("ABC1234"), "ALLOW")
        self.assertLess(time.perf_counter() - started, 2.0)


class ParkingHistoryTests(AppTestCase):
    """SR-08, SR-15: a driver sees only their own parking history, read only."""

    def test_driver_sees_only_own_history(self):
        dana = self.new_driver("dana@test.example")
        vehicle = self.add_vehicle(dana, "ABC1234")
        omar = self.new_driver("omar@test.example")
        self.reserve(dana, vehicle)
        self.clock.advance(hours=2, minutes=5)
        self.assertEqual(self.decision("ABC1234"), "ALLOW")

        dana, omar = self.login("dana@test.example"), self.login("omar@test.example")
        history = dana.get("/api/parking-history").get_json()["parking_sessions"]
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["spot"], "A-01")
        self.assertIsNone(history[0]["exit"])
        self.assertNotIn("ABC1234", dana.get("/api/parking-history").get_data(as_text=True))
        self.assertEqual(omar.get("/api/parking-history").get_json()["parking_sessions"], [])

        # No route changes a parking session (SR-15).
        for method in ("PUT", "PATCH", "DELETE", "POST"):
            response = dana.open(f"/api/parking-history/{history[0]['id']}", method=method, json={})
            self.assertIn(response.status_code, (404, 405), method)
        self.assertEqual(len(self.query("SELECT id FROM parking_sessions")), 1)


if __name__ == "__main__":
    unittest.main()
