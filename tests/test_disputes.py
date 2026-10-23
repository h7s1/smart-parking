"""Disputes and support agent access (FR-15, FR-16, FR-17, SR-09, NFR-08, TH-10)."""
import unittest
import uuid

from helpers import ADMIN_EMAIL, PASSWORD, SUPPORT_EMAIL, AppTestCase

REASON = "RESERVED_SPOT_TAKEN"


class DisputeTests(AppTestCase):

    def setUp(self):
        super().setUp()
        self.dana = self.new_driver("dana@test.example")
        self.omar = self.new_driver("omar@test.example")
        self.dana_vehicle = self.add_vehicle(self.dana, "DAN1001")
        self.omar_vehicle = self.add_vehicle(self.omar, "OMR2002")
        self.dana_reservation = self.reserve(self.dana, self.dana_vehicle).get_json()["reservation"]["id"]
        self.omar_reservation = self.reserve(
            self.omar, self.omar_vehicle, spot_label="A-02").get_json()["reservation"]["id"]
        self.support = self.login(SUPPORT_EMAIL)
        self.dana_id = self.user_id_owning(self.dana_vehicle)
        self.omar_id = self.user_id_owning(self.omar_vehicle)

    def user_id_owning(self, vehicle_id):
        return self.query("SELECT owner_id FROM vehicles WHERE id = ?", (vehicle_id,))[0]["owner_id"]

    def open_dispute(self, client, reason=REASON, **subject):
        if not subject:
            subject = {"reservation_id": self.dana_reservation}
        return client.post("/api/disputes", json={"reason": reason, **subject})

    def audit(self, action):
        return self.query("SELECT user_id, target_id FROM audit_log WHERE action = ?", (action,))

    def record(self, dispute_id, client=None):
        """SR-09: what a support agent sees for one dispute."""
        return (client or self.support).get(f"/api/support/disputes/{dispute_id}/record")

    # ----- FR-15: drivers open disputes -----

    def test_driver_opens_dispute_about_own_reservation(self):
        """FR-15"""
        response = self.open_dispute(self.dana)
        self.assertEqual(response.status_code, 201)
        dispute = response.get_json()["dispute"]
        self.assertEqual(dispute["status"], "OPEN")
        mine = self.dana.get("/api/disputes").get_json()["disputes"]
        self.assertEqual([d["id"] for d in mine], [dispute["id"]])
        self.assertEqual(mine[0]["record_id"], self.dana_reservation)
        self.assertEqual(self.audit("DISPUTE_OPENED")[0]["user_id"], self.dana_id)

    def test_driver_opens_dispute_about_own_parking_session(self):
        """FR-15"""
        self.clock.advance(hours=2, minutes=5)
        self.assertEqual(self.decision("DAN1001"), "ALLOW")
        dana = self.login("dana@test.example")
        session_id = dana.get("/api/parking-history").get_json()["parking_sessions"][0]["id"]
        response = self.open_dispute(dana, "WRONG_ENTRY_OR_EXIT_TIME", parking_session_id=session_id)
        self.assertEqual(response.status_code, 201)

    def test_reason_must_come_from_the_fixed_list(self):
        """FR-15, PR-02 (negative): no free text can be stored."""
        for reason in ("My neighbour Ahmed took my spot, call 0500000000", "", None, 5):
            self.assertEqual(self.open_dispute(self.dana, reason).status_code, 400, reason)
        both = {"reservation_id": self.dana_reservation, "parking_session_id": str(uuid.uuid4())}
        self.assertEqual(self.dana.post("/api/disputes", json={"reason": REASON, **both}).status_code, 400)
        self.assertEqual(self.dana.post("/api/disputes", json={"reason": REASON}).status_code, 400)
        extra = self.dana.post("/api/disputes", json={"reason": REASON, "comment": "free text",
                                                      "reservation_id": self.dana_reservation})
        self.assertEqual(extra.status_code, 201)            # the extra field is ignored
        self.assertNotIn("free text", str([tuple(r) for r in self.query("SELECT * FROM disputes")]))
        self.assertEqual(len(self.query("SELECT id FROM disputes")), 1)

    def test_driver_cannot_dispute_another_drivers_record(self):
        """FR-15, SR-08 (negative)"""
        response = self.open_dispute(self.omar, reservation_id=self.dana_reservation)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.query("SELECT id FROM disputes"), [])

    def test_only_one_open_dispute_per_record(self):
        self.assertEqual(self.open_dispute(self.dana).status_code, 201)
        self.assertEqual(self.open_dispute(self.dana, "RESERVATION_NOT_SHOWN").status_code, 409)

    # ----- FR-16, SR-09, NFR-08: support agent -----

    def test_support_sees_all_open_disputes(self):
        """FR-16: with driver IDs only, never emails."""
        self.open_dispute(self.dana)
        self.open_dispute(self.omar, reservation_id=self.omar_reservation)
        response = self.support.get("/api/support/disputes")
        disputes = response.get_json()["disputes"]
        self.assertEqual({d["driver_id"] for d in disputes}, {self.dana_id, self.omar_id})
        self.assertNotIn("@test.example", response.get_data(as_text=True))

    def test_support_sees_only_the_disputed_record(self):
        """SR-09, TH-10: the one reservation and its car's plate, nothing else about the driver."""
        # Dana has a second car and a second reservation that the dispute is not about.
        dana_car2 = self.add_vehicle(self.dana, "DAN3003")
        other = self.reserve(self.dana, dana_car2, spot_label="A-02", start_in_hours=5).get_json()
        other_reservation = other["reservation"]["id"]
        dispute_id = self.open_dispute(self.dana).get_json()["dispute"]["id"]

        response = self.record(dispute_id)
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(set(data), {"dispute_id", "about", "record", "plate"})
        self.assertEqual(data["about"], "RESERVATION")
        self.assertEqual(data["record"]["id"], self.dana_reservation)
        self.assertEqual(data["record"]["spot"], "A-01")
        self.assertEqual(data["plate"], "DAN1001")
        body = response.get_data(as_text=True)
        self.assertNotIn(other_reservation, body)              # not the other reservation
        self.assertNotIn("DAN3003", body)                      # not the other car
        self.assertNotIn(self.dana_id, body)                   # not even the driver ID
        self.assertNotIn("dana@", body)
        self.assertNotIn("$2b$", body)
        self.assertNotIn("OMR2002", body)                      # nothing about other drivers

    def test_support_sees_the_disputed_visit(self):
        """SR-09: a dispute about a parking session shows that visit and its car's plate."""
        self.clock.advance(hours=2, minutes=5)
        self.assertEqual(self.decision("DAN1001"), "ALLOW")
        dana = self.login("dana@test.example")
        session_id = dana.get("/api/parking-history").get_json()["parking_sessions"][0]["id"]
        dispute = self.open_dispute(dana, "WRONG_ENTRY_OR_EXIT_TIME", parking_session_id=session_id)
        support = self.login(SUPPORT_EMAIL)                     # the first session timed out (SR-05)
        data = self.record(dispute.get_json()["dispute"]["id"], support).get_json()
        self.assertEqual(data["about"], "PARKING_SESSION")
        self.assertEqual(data["record"]["id"], session_id)
        self.assertIsNotNone(data["record"]["entry"])
        self.assertIsNone(data["record"]["exit"])              # the car is still inside
        self.assertEqual(data["plate"], "DAN1001")

    def test_no_record_without_an_open_dispute(self):
        """SR-09, TH-10 (negative): a closed dispute and an unknown ID get the same refusal."""
        dispute_id = self.open_dispute(self.dana).get_json()["dispute"]["id"]
        self.support.post(f"/api/support/disputes/{dispute_id}/close", json={})
        for some_id in (dispute_id, str(uuid.uuid4())):
            response = self.record(some_id)
            self.assertEqual(response.status_code, 403)
            self.assertNotIn("record", response.get_json())
            self.assertNotIn("DAN1001", response.get_data(as_text=True))
        self.assertEqual(self.record("1 OR 1=1").status_code, 404)

    def test_every_support_access_is_recorded(self):
        """NFR-08, TH-07: allowed and refused attempts both go to the audit log."""
        support_id = self.query("SELECT user_id FROM audit_log WHERE action = 'LOGIN_SUCCESS'"
                                " ORDER BY rowid DESC LIMIT 1")[0]["user_id"]
        dispute_id = self.open_dispute(self.dana).get_json()["dispute"]["id"]
        unknown_id = str(uuid.uuid4())
        self.record(dispute_id)
        self.record(unknown_id)
        allowed, denied = self.audit("SUPPORT_ACCESS"), self.audit("SUPPORT_ACCESS_DENIED")
        self.assertEqual([(r["user_id"], r["target_id"]) for r in allowed], [(support_id, dispute_id)])
        self.assertEqual([(r["user_id"], r["target_id"]) for r in denied], [(support_id, unknown_id)])

    def test_closing_the_dispute_ends_access(self):
        """FR-17, SR-09"""
        dispute_id = self.open_dispute(self.dana).get_json()["dispute"]["id"]
        self.assertEqual(self.record(dispute_id).status_code, 200)
        response = self.support.post(f"/api/support/disputes/{dispute_id}/close", json={})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.support.get("/api/support/disputes").get_json()["disputes"], [])
        self.assertEqual(self.record(dispute_id).status_code, 403)
        mine = self.dana.get("/api/disputes").get_json()["disputes"][0]
        self.assertEqual(mine["status"], "CLOSED")
        self.assertIsNotNone(mine["closed"])
        self.assertEqual(self.audit("DISPUTE_CLOSED")[0]["target_id"], dispute_id)

    def test_closing_a_closed_or_missing_dispute_is_refused(self):
        """Safe messages, nothing changes."""
        dispute_id = self.open_dispute(self.dana).get_json()["dispute"]["id"]
        self.support.post(f"/api/support/disputes/{dispute_id}/close", json={})
        again = self.support.post(f"/api/support/disputes/{dispute_id}/close", json={})
        self.assertEqual(again.status_code, 409)
        self.assertEqual(again.get_json()["error"], "This dispute is already closed.")
        for bad_id in (str(uuid.uuid4()), "1 OR 1=1"):
            self.assertEqual(self.support.post(f"/api/support/disputes/{bad_id}/close", json={}).status_code, 404)

    # ----- SR-07: least privilege -----

    def test_drivers_and_admin_cannot_use_support_functions(self):
        """SR-07, TH-10 (negative)"""
        dispute_id = self.open_dispute(self.dana).get_json()["dispute"]["id"]
        admin = self.login(ADMIN_EMAIL)
        for client in (self.dana, self.omar, admin):
            self.assertEqual(client.get("/api/support/disputes").status_code, 403)
            self.assertEqual(self.record(dispute_id, client).status_code, 403)
            self.assertEqual(client.post(f"/api/support/disputes/{dispute_id}/close", json={}).status_code, 403)
        self.assertEqual(self.audit("SUPPORT_ACCESS"), [])
        self.assertEqual(self.query("SELECT status FROM disputes")[0]["status"], "OPEN")

    def test_support_cannot_use_driver_or_admin_functions(self):
        """SR-07 (negative)"""
        self.assertEqual(self.open_dispute(self.support).status_code, 403)
        self.assertEqual(self.support.get("/api/parking-history").status_code, 403)
        self.assertEqual(self.support.get("/api/disputes").status_code, 403)
        self.assertEqual(self.support.patch(f"/api/admin/spots/{self.spot_ids['A-01']}",
                                            json={"status": "DISABLED"}).status_code, 403)

    def test_support_has_no_route_that_changes_driver_records(self):
        """SR-15: the only support action that changes anything is closing a dispute."""
        changing = {
            rule.rule for rule in self.app.url_map.iter_rules()
            if rule.rule.startswith("/api/support/") and rule.methods & {"POST", "PUT", "PATCH", "DELETE"}
        }
        self.assertEqual(changing, {"/api/support/disputes/<dispute_id>/close"})

    # ----- D9: the admin sees dispute actions; PR-11: deleted with the account -----

    def test_admin_audit_log_shows_dispute_actions_by_id_only(self):
        """NFR-07, NFR-08, PR-06"""
        dispute_id = self.open_dispute(self.dana).get_json()["dispute"]["id"]
        self.record(dispute_id)
        self.support.post(f"/api/support/disputes/{dispute_id}/close", json={})
        response = self.login(ADMIN_EMAIL).get("/api/admin/audit-log")
        actions = {entry["action"] for entry in response.get_json()["entries"]}
        self.assertTrue({"DISPUTE_OPENED", "SUPPORT_ACCESS", "DISPUTE_CLOSED"} <= actions)
        body = response.get_data(as_text=True)
        self.assertNotIn("@test.example", body)
        self.assertNotIn("DAN1001", body)

    def test_deleting_the_account_deletes_the_disputes(self):
        """PR-11"""
        self.open_dispute(self.dana)
        self.assertEqual(self.dana.post("/api/account/delete", json={"password": PASSWORD}).status_code, 200)
        self.assertEqual(self.query("SELECT id FROM disputes"), [])


if __name__ == "__main__":
    unittest.main()
