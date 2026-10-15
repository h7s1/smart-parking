"""Roles and ownership: who can do what (SR-03, SR-07 to SR-10, SR-12, SR-14)."""
import re
import unittest
import uuid

from helpers import ADMIN_EMAIL, SUPPORT_EMAIL, AppTestCase

PUBLIC_ROUTES = {"/api/register", "/api/login"}
GATE_ROUTES = {"/api/gate/events"}          # protected by the gate key instead (SR-20)


class RoleTests(AppTestCase):

    def setUp(self):
        super().setUp()
        self.driver = self.new_driver("dana@test.example")
        self.admin = self.login(ADMIN_EMAIL)
        self.support = self.login(SUPPORT_EMAIL)
        self.spot = self.spot_ids["A-01"]

    def test_every_api_route_needs_login(self):
        """SR-03, fail-safe default (negative): no route was left without a guard."""
        stranger = self.client()
        fake_id = str(uuid.uuid4())
        for rule in self.app.url_map.iter_rules():
            path = rule.rule
            if not path.startswith("/api/") or path in PUBLIC_ROUTES | GATE_ROUTES:
                continue
            url = re.sub(r"<[^>]+>", fake_id, path)
            for method in rule.methods - {"HEAD", "OPTIONS"}:
                response = stranger.open(url, method=method, json={})
                self.assertEqual(response.status_code, 401, f"{method} {path}")

    def test_gate_route_needs_gate_key_not_a_login(self):
        """SR-20: a logged-in user without the gate key is refused too."""
        for browser in (self.client(), self.driver, self.admin, self.support):
            with self.assertLogs(self.app.logger, level="WARNING"):
                response = browser.post("/api/gate/events", json={"plate": "ABC1234", "direction": "ENTRY"})
            self.assertEqual(response.status_code, 401)

    def test_driver_cannot_use_admin_functions(self):
        """SR-07, TH-11 (negative)"""
        self.assertEqual(self.driver.get("/api/admin/spots").status_code, 403)
        self.assertEqual(self.driver.patch(f"/api/admin/spots/{self.spot}", json={"status": "DISABLED"}).status_code, 403)
        self.assertEqual(self.driver.get("/api/admin/audit-log").status_code, 403)
        status = self.query("SELECT status FROM spots WHERE id = ?", (self.spot,))[0]["status"]
        self.assertEqual(status, "FREE")

    def test_support_agent_cannot_use_admin_or_driver_functions(self):
        """SR-07, least privilege (negative)"""
        for path in ("/api/admin/spots", "/api/admin/audit-log", "/api/vehicles", "/api/reservations"):
            self.assertEqual(self.support.get(path).status_code, 403, path)

    def test_admin_cannot_use_driver_functions(self):
        """SR-07, least privilege (negative): the admin cannot see plates or reservations."""
        self.assertEqual(self.admin.get("/api/vehicles").status_code, 403)
        self.assertEqual(self.admin.get("/api/reservations").status_code, 403)
        self.assertEqual(self.admin.post("/api/vehicles", json={"plate": "ADM1"}).status_code, 403)

    def test_only_admin_reads_audit_log(self):
        """SR-12, FR-14"""
        response = self.admin.get("/api/admin/audit-log")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["entries"])

    def test_admin_spot_view_hides_driver_identity(self):
        """SR-14, FR-12: reserved times only."""
        vehicle_id = self.add_vehicle(self.driver, "ABC1234")
        self.assertEqual(self.reserve(self.driver, vehicle_id).status_code, 201)

        spots = self.admin.get("/api/admin/spots").get_json()["spots"]
        spot = next(s for s in spots if s["label"] == "A-01")
        self.assertEqual(len(spot["reserved_times"]), 1)
        self.assertEqual(set(spot["reserved_times"][0]), {"start", "end"})
        body = self.admin.get("/api/admin/spots").get_data(as_text=True)
        self.assertNotIn(vehicle_id, body)
        self.assertNotIn("ABC1234", body)
        self.assertNotIn("dana", body)


class OwnershipTests(AppTestCase):
    """SR-08, TH-08: a driver changes an ID in a request (IDOR)."""

    def setUp(self):
        super().setUp()
        self.alice = self.new_driver("alice@test.example")
        self.bob = self.new_driver("bob@test.example")
        self.alice_vehicle = self.add_vehicle(self.alice, "ALC1001")
        response = self.reserve(self.alice, self.alice_vehicle)
        self.alice_reservation = response.get_json()["reservation"]["id"]

    def test_driver_cannot_cancel_another_drivers_reservation(self):
        response = self.bob.delete(f"/api/reservations/{self.alice_reservation}")
        self.assertEqual(response.status_code, 404)          # same answer as "does not exist"
        self.assertEqual(len(self.query("SELECT id FROM reservations")), 1)

    def test_driver_cannot_remove_another_drivers_vehicle(self):
        response = self.bob.delete(f"/api/vehicles/{self.alice_vehicle}")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(len(self.query("SELECT id FROM vehicles")), 1)

    def test_driver_cannot_reserve_with_another_drivers_vehicle(self):
        response = self.reserve(self.bob, self.alice_vehicle, spot_label="A-02")
        self.assertEqual(response.status_code, 404)

    def test_driver_lists_only_own_records(self):
        self.assertEqual(self.bob.get("/api/vehicles").get_json()["vehicles"], [])
        self.assertEqual(self.bob.get("/api/reservations").get_json()["reservations"], [])
        self.assertEqual(len(self.alice.get("/api/reservations").get_json()["reservations"]), 1)

    def test_ids_are_random_uuids(self):
        """SR-10: IDs cannot be guessed from one another."""
        self.clock.advance(hours=2)                       # the reservation has started
        self.assertEqual(self.decision("ALC1001"), "ALLOW")
        alice = self.login("alice@test.example")         # the old session timed out
        session_id = alice.get("/api/parking-history").get_json()["parking_sessions"][0]["id"]
        alice.post("/api/disputes", json={"parking_session_id": session_id,
                                          "reason": "WRONG_ENTRY_OR_EXIT_TIME"})
        for table in ("users", "vehicles", "reservations", "spots", "parking_sessions",
                      "disputes", "audit_log"):
            self.assertTrue(self.query(f"SELECT id FROM {table}"), table)
            for row in self.query(f"SELECT id FROM {table}"):
                self.assertEqual(uuid.UUID(row["id"]).version, 4, table)


if __name__ == "__main__":
    unittest.main()
