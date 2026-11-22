"""Week 13: retests for the two problems found in the final review.

1. Cancelling a reservation, or removing a vehicle, deleted an open dispute
   about it without a trace (ON DELETE CASCADE), although the Personal Data
   Map keeps such a record until the dispute is closed (PR-08, SR-09).
2. A spot that was OCCUPIED at the moment of booking could not be reserved
   for a later time (FR-06).

All data is synthetic.
"""
import unittest

from helpers import SUPPORT_EMAIL, AppTestCase

REASON = "RESERVED_SPOT_TAKEN"


class OpenDisputeKeepsItsRecord(AppTestCase):
    """PR-08, SR-09: a record with an open dispute stays until the dispute is closed."""

    def setUp(self):
        super().setUp()
        self.dana = self.new_driver("dana@test.example")
        self.vehicle = self.add_vehicle(self.dana, "DAN1001")
        self.reservation = self.reserve(
            self.dana, self.vehicle, start_in_hours=5).get_json()["reservation"]["id"]
        response = self.dana.post("/api/disputes",
                                  json={"reason": REASON, "reservation_id": self.reservation})
        self.assertEqual(response.status_code, 201)
        self.dispute = response.get_json()["dispute"]["id"]

    def dispute_status(self):
        rows = self.query("SELECT status FROM disputes WHERE id = ?", (self.dispute,))
        return rows[0]["status"] if rows else None

    def test_reservation_with_open_dispute_cannot_be_cancelled(self):
        """FR-07, PR-08 (negative, then positive): the cancel is refused while
        the dispute is open, and allowed after the support agent closes it."""
        response = self.dana.delete(f"/api/reservations/{self.reservation}")
        self.assertEqual(response.status_code, 409)
        self.assertIn("open dispute", response.get_json()["error"])
        self.assertEqual(self.dispute_status(), "OPEN")
        self.assertEqual(len(self.query("SELECT id FROM reservations")), 1)

        support = self.login(SUPPORT_EMAIL)
        self.assertEqual(
            support.post(f"/api/support/disputes/{self.dispute}/close", json={}).status_code, 200)
        self.assertEqual(self.dana.delete(f"/api/reservations/{self.reservation}").status_code, 200)
        self.assertEqual(len(self.query("SELECT id FROM reservations")), 0)

    def test_vehicle_with_open_dispute_cannot_be_removed(self):
        """FR-05, PR-08 (negative, then positive): removing the car is refused
        while one of its records has an open dispute."""
        response = self.dana.delete(f"/api/vehicles/{self.vehicle}")
        self.assertEqual(response.status_code, 409)
        self.assertIn("open dispute", response.get_json()["error"])
        self.assertEqual(self.dispute_status(), "OPEN")
        self.assertEqual(len(self.query("SELECT id FROM vehicles")), 1)

        support = self.login(SUPPORT_EMAIL)
        self.assertEqual(
            support.post(f"/api/support/disputes/{self.dispute}/close", json={}).status_code, 200)
        self.assertEqual(self.dana.delete(f"/api/vehicles/{self.vehicle}").status_code, 200)
        self.assertEqual(len(self.query("SELECT id FROM vehicles")), 0)


class OccupiedSpotCanBeReservedForLater(AppTestCase):

    def test_spot_occupied_now_can_be_reserved_for_a_later_time(self):
        """FR-06 (positive, then negative): a spot with a car in it now can be
        reserved for a later time, but the overlap check and the DISABLED
        status still refuse a reservation."""
        omar = self.new_driver("omar@test.example")
        omar_vehicle = self.add_vehicle(omar, "OMR2002")
        self.assertEqual(self.reserve(omar, omar_vehicle, start_in_hours=1).status_code, 201)
        self.clock.advance(hours=1, minutes=5)
        self.assertEqual(self.decision("OMR2002"), "ALLOW")
        status = self.query("SELECT status FROM spots WHERE id = ?", (self.spot_ids["A-01"],))
        self.assertEqual(status[0]["status"], "OCCUPIED")

        dana = self.new_driver("dana@test.example")
        dana_vehicle = self.add_vehicle(dana, "DAN1001")
        listed = [s["label"] for s in dana.get("/api/spots").get_json()["spots"]]
        self.assertEqual(listed, ["A-01", "A-02"])          # A-03 is DISABLED
        self.assertEqual(self.reserve(dana, dana_vehicle, start_in_hours=24).status_code, 201)

        # Omar's reservation still covers the next 55 minutes: overlap refused.
        self.assertEqual(self.reserve(dana, dana_vehicle, start_in_hours=0.5).status_code, 409)
        # A DISABLED spot is still refused.
        self.assertEqual(
            self.reserve(dana, dana_vehicle, spot_label="A-03", start_in_hours=48).status_code, 409)


if __name__ == "__main__":
    unittest.main()
