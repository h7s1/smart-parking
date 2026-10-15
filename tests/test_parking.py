"""Vehicles, reservations and spot administration (FR-04 to FR-07, FR-12, FR-13, NFR-03, NFR-09)."""
import unittest
from datetime import timedelta

from helpers import ADMIN_EMAIL, AppTestCase, iso


class VehicleTests(AppTestCase):

    def setUp(self):
        super().setUp()
        self.driver = self.new_driver("dana@test.example")

    def test_add_list_and_remove_vehicle(self):
        """FR-04, FR-05"""
        vehicle_id = self.add_vehicle(self.driver, "abc 1234")
        vehicles = self.driver.get("/api/vehicles").get_json()["vehicles"]
        self.assertEqual(vehicles, [{"id": vehicle_id, "plate": "ABC1234"}])
        self.assertEqual(self.driver.delete(f"/api/vehicles/{vehicle_id}").status_code, 200)
        self.assertEqual(self.driver.get("/api/vehicles").get_json()["vehicles"], [])

    def test_plate_must_be_unique(self):
        """FR-04 (negative): also across different drivers."""
        self.add_vehicle(self.driver, "ABC1234")
        other = self.new_driver("omar@test.example")
        response = other.post("/api/vehicles", json={"plate": "abc-1234"})
        self.assertEqual(response.status_code, 409)

    def test_plate_stored_only_encrypted(self):
        """PR-04"""
        self.add_vehicle(self.driver, "ABC1234")
        stored = self.query("SELECT plate_enc FROM vehicles")[0]["plate_enc"]
        self.assertNotIn("ABC1234", stored)

    def test_invalid_plate_rejected(self):
        """SR-17, NFR-04 (negative)"""
        for plate in ("", "A", "ABCDEFGHIJK", "AB$12", 1234):
            response = self.driver.post("/api/vehicles", json={"plate": plate})
            self.assertEqual(response.status_code, 400, plate)


class ReservationTests(AppTestCase):

    def setUp(self):
        super().setUp()
        self.driver = self.new_driver("dana@test.example")
        self.vehicle = self.add_vehicle(self.driver, "ABC1234")

    def test_reserve_free_spot_with_confirmation(self):
        """FR-06, NFR-03"""
        response = self.reserve(self.driver, self.vehicle)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["message"], "Reservation confirmed.")

    def test_cannot_reserve_disabled_spot(self):
        """FR-06 (negative)"""
        self.assertEqual(self.reserve(self.driver, self.vehicle, spot_label="A-03").status_code, 409)

    def test_overlapping_reservations_rejected(self):
        """NFR-09 (negative): two drivers, same spot, overlapping times."""
        other = self.new_driver("omar@test.example")
        other_vehicle = self.add_vehicle(other, "XYZ9876")
        self.assertEqual(self.reserve(self.driver, self.vehicle, start_in_hours=2, hours=2).status_code, 201)
        self.assertEqual(self.reserve(other, other_vehicle, start_in_hours=3, hours=2).status_code, 409)

    def test_back_to_back_reservations_allowed(self):
        """NFR-09: one booking may start exactly when the previous one ends."""
        self.assertEqual(self.reserve(self.driver, self.vehicle, start_in_hours=2, hours=1).status_code, 201)
        self.assertEqual(self.reserve(self.driver, self.vehicle, start_in_hours=3, hours=1).status_code, 201)

    def test_cancel_up_to_30_minutes_before_start(self):
        """FR-07, NFR-03"""
        reservation_id = self.reserve(self.driver, self.vehicle, start_in_hours=2).get_json()["reservation"]["id"]
        self.clock.advance(hours=1, minutes=30)                    # exactly 30 minutes left
        self.driver = self.login("dana@test.example")              # the old session timed out
        response = self.driver.delete(f"/api/reservations/{reservation_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["message"], "Reservation cancelled.")

    def test_cannot_cancel_less_than_30_minutes_before_start(self):
        """FR-07 (negative)"""
        reservation_id = self.reserve(self.driver, self.vehicle, start_in_hours=2).get_json()["reservation"]["id"]
        self.clock.advance(hours=1, minutes=31)                    # 29 minutes left
        self.driver = self.login("dana@test.example")              # the old session timed out
        self.assertEqual(self.driver.delete(f"/api/reservations/{reservation_id}").status_code, 409)

    def test_invalid_times_rejected(self):
        """NFR-04, SR-17 (negative)"""
        now = self.clock()
        cases = [
            (iso(now - timedelta(hours=1)), iso(now + timedelta(hours=1))),      # starts in the past
            (iso(now + timedelta(hours=3)), iso(now + timedelta(hours=2))),      # ends before it starts
            (iso(now + timedelta(hours=1)), iso(now + timedelta(hours=30))),     # longer than 24 hours
            ("2026-10-20T10:00:00", "2026-10-20T11:00:00"),                       # no time zone
            ("tomorrow", "later"),
            ("9999-12-31T23:59:59-05:00", "9999-12-31T23:59:59-04:00"),           # out of range
        ]
        for start, end in cases:
            response = self.driver.post("/api/reservations", json={
                "vehicle_id": self.vehicle, "spot_id": self.spot_ids["A-01"], "start": start, "end": end})
            self.assertEqual(response.status_code, 400, (start, end))


class AdminSpotTests(AppTestCase):

    def setUp(self):
        super().setUp()
        self.admin = self.login(ADMIN_EMAIL)

    def test_admin_sees_status_of_every_spot(self):
        """FR-12"""
        spots = self.admin.get("/api/admin/spots").get_json()["spots"]
        self.assertEqual({s["label"]: s["status"] for s in spots},
                         {"A-01": "FREE", "A-02": "FREE", "A-03": "DISABLED"})

    def test_admin_switches_spot_between_free_and_disabled(self):
        """FR-13"""
        spot = self.spot_ids["A-01"]
        self.assertEqual(self.admin.patch(f"/api/admin/spots/{spot}", json={"status": "DISABLED"}).status_code, 200)
        self.assertEqual(self.admin.patch(f"/api/admin/spots/{spot}", json={"status": "FREE"}).status_code, 200)

    def test_admin_cannot_set_other_statuses(self):
        """FR-13 (negative)"""
        spot = self.spot_ids["A-01"]
        response = self.admin.patch(f"/api/admin/spots/{spot}", json={"status": "OCCUPIED"})
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
