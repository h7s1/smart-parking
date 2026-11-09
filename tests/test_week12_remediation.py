"""Week 12: retests for the remediation of the review findings.

Each test names the finding it retests (Table 35 in the report). Positive
tests show that the allowed action works; negative tests show that the attack
or the mistake is refused. All data is synthetic.
"""
import json
import unittest

from helpers import ADMIN_EMAIL, PASSWORD, SUPPORT_EMAIL, AppTestCase


class PasswordBlocklist(AppTestCase):
    """SR-06 and F-04 (Week 12): new passwords are checked against a list of
    common and easy-to-guess passwords, as NIST SP 800-63B-4 asks."""

    def assert_refused(self, password, email="dana@test.example"):
        response = self.register(email, password)
        self.assertEqual(response.status_code, 400, password)
        self.assertIn("too common", response.get_json()["error"])

    def test_common_passwords_are_refused(self):
        """SR-06 (negative): passwords from the common list are refused."""
        for password in ("password123", "12345678", "qwerty123", "iloveyou"):
            self.assert_refused(password)

    def test_variants_of_common_passwords_are_refused(self):
        """SR-06 (negative): numbers or symbols at the end, and letter swaps, do not help."""
        for password in ("Welcome2026!", "P@ssw0rd", "Admin@12345", "Qwerty!!99"):
            self.assert_refused(password)

    def test_repeated_and_sequence_passwords_are_refused(self):
        """SR-06 (negative): one repeated character or a simple sequence is refused."""
        for password in ("aaaaaaaa", "23456789", "abcdefghij"):
            self.assert_refused(password)

    def test_service_name_and_email_name_are_refused(self):
        """SR-06 (negative): the name of the service or of the user is refused."""
        self.assert_refused("MySmartParking1")
        self.assert_refused("dana.secret.77", email="dana@test.example")

    def test_ordinary_password_is_accepted(self):
        """SR-06 (positive): an 8-character password that is not on the list is accepted."""
        self.assertEqual(self.register("dana@test.example", "tulip-rain").status_code, 201)
        self.login("dana@test.example", "tulip-rain")


class WorkEmailOnly(AppTestCase):
    """F-08 (fixed in Week 12): only work emails of the business complex can register."""

    def test_work_email_can_register(self):
        """F-08 (positive): an email with the domain of the complex gets a driver account."""
        self.assertEqual(self.register("dana@test.example").status_code, 201)
        self.login("dana@test.example")

    def test_similar_domain_is_refused(self):
        """F-08 (negative): a domain that only looks like the complex's domain is refused."""
        for email in ("dana@test.example.com", "dana@fake-test.example", "dana@mail.test.example"):
            self.assertEqual(self.register(email).status_code, 400, email)


class PrivacyNotice(AppTestCase):
    """P-01 (fixed in Week 12): a privacy notice is shown before registration."""

    def test_create_account_tab_has_the_privacy_notice(self):
        """P-01: the page has the notice and a required "I have read" box."""
        page = self.client().get("/").get_data(as_text=True)
        self.assertIn('id="privacy-notice"', page)
        for text in ("What we collect", "Why", "Who can see it", "How long we keep it",
                     "What you can do", "kept for 180 days"):
            self.assertIn(text, page)
        self.assertIn('name="notice_read" required', page)


class DownloadMyData(AppTestCase):
    """P-02 (fixed in Week 12): a driver can download a copy of their own data."""

    def setUp(self):
        super().setUp()
        self.dana = self.new_driver("dana@test.example")
        self.omar = self.new_driver("omar@test.example")
        vehicle = self.add_vehicle(self.dana, "DAN1001")
        self.add_vehicle(self.omar, "OMR2002")
        self.reserve(self.dana, vehicle, start_in_hours=1)
        self.clock.advance(hours=1, minutes=5)
        self.assertEqual(self.decision("DAN1001"), "ALLOW")         # a visit for the history
        self.clock.advance(minutes=30)
        self.assertEqual(self.decision("DAN1001", "EXIT"), "ALLOW")
        self.dana = self.login("dana@test.example")      # the first session timed out meanwhile

    def test_driver_downloads_own_data(self):
        """P-02 (positive): the file has the driver's account, vehicle, reservation and visit."""
        response = self.dana.post("/api/account/export", json={"password": PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response.headers["Content-Disposition"])
        data = response.get_json()
        self.assertEqual(data["account"]["email"], "dana@test.example")
        self.assertEqual([v["plate"] for v in data["vehicles"]], ["DAN1001"])
        self.assertEqual(len(data["reservations"]), 1)
        self.assertEqual(data["parking_history"][0]["plate"], "DAN1001")
        self.assertIn("180 days", data["note"])

    def test_download_has_no_other_driver_data_and_no_internal_ids(self):
        """P-02, SR-08 (negative): nothing about another driver, and no user IDs."""
        text = json.dumps(self.dana.post("/api/account/export", json={"password": PASSWORD}).get_json())
        self.assertNotIn("OMR2002", text)
        self.assertNotIn("omar@test.example", text)
        dana_id = self.query("SELECT owner_id FROM vehicles")[0]["owner_id"]
        self.assertNotIn(dana_id, text)

    def test_download_needs_the_password_and_is_recorded(self):
        """P-02 (negative): a wrong password gets nothing; a download is in the audit log."""
        self.assertEqual(self.dana.post("/api/account/export", json={"password": "not my password"}).status_code, 400)
        self.dana.post("/api/account/export", json={"password": PASSWORD})
        self.assertEqual(len(self.query("SELECT id FROM audit_log WHERE action = 'DATA_EXPORTED'")), 1)

    def test_download_is_for_drivers_only(self):
        """P-02, SR-07 (negative): no session gets 401; admin and support agent get 403."""
        self.assertEqual(self.client().post("/api/account/export", json={"password": PASSWORD}).status_code, 401)
        for email in (ADMIN_EMAIL, SUPPORT_EMAIL):
            staff = self.login(email)
            self.assertEqual(staff.post("/api/account/export", json={"password": PASSWORD}).status_code, 403)


class ChangePassword(AppTestCase):
    """P-03 (fixed in Week 12): a driver can change their password."""

    NEW = "blue harbour lamp"

    def setUp(self):
        super().setUp()
        self.dana = self.new_driver("dana@test.example")

    def change(self, client, current, new):
        return client.post("/api/account/password", json={"current_password": current, "new_password": new})

    def test_password_change_works_and_ends_other_sessions(self):
        """P-03 (positive): the new password works, the old one does not, and the
        driver's other sessions end while this one continues."""
        other_device = self.login("dana@test.example")
        self.assertEqual(self.change(self.dana, PASSWORD, self.NEW).status_code, 200)
        self.assertEqual(other_device.get("/api/me").status_code, 401)
        self.assertEqual(self.dana.get("/api/me").status_code, 200)
        old = self.client().post("/api/login", json={"email": "dana@test.example", "password": PASSWORD})
        self.assertEqual(old.status_code, 401)
        self.login("dana@test.example", self.NEW)
        self.assertEqual(len(self.query("SELECT id FROM audit_log WHERE action = 'PASSWORD_CHANGED'")), 1)

    def test_wrong_current_password_or_common_new_password_is_refused(self):
        """P-03, SR-06 (negative): a wrong current password or a common new one changes nothing."""
        self.assertEqual(self.change(self.dana, "not my password", self.NEW).status_code, 400)
        self.assertEqual(self.change(self.dana, PASSWORD, "password123").status_code, 400)
        self.login("dana@test.example", PASSWORD)                    # the old password still works


class ChangeEmail(AppTestCase):
    """P-03 (fixed in Week 12): a driver can correct their email."""

    def setUp(self):
        super().setUp()
        self.dana = self.new_driver("dana@test.example")
        self.new_driver("omar@test.example")

    def change(self, email, password=PASSWORD):
        return self.dana.post("/api/account/email", json={"email": email, "password": password})

    def test_email_change_works(self):
        """P-03 (positive): the driver logs in with the new email, and the change is recorded."""
        self.assertEqual(self.change("dana.ali@test.example").status_code, 200)
        self.assertEqual(self.dana.get("/api/me").get_json()["email"], "dana.ali@test.example")
        self.login("dana.ali@test.example")
        old = self.client().post("/api/login", json={"email": "dana@test.example", "password": PASSWORD})
        self.assertEqual(old.status_code, 401)
        self.assertEqual(len(self.query("SELECT id FROM audit_log WHERE action = 'EMAIL_CHANGED'")), 1)

    def test_bad_email_changes_are_refused(self):
        """P-03, F-08, SR-19 (negative): a wrong password, an email from outside the
        complex, or another driver's email is refused."""
        self.assertEqual(self.change("dana.ali@test.example", "not my password").status_code, 400)
        self.assertEqual(self.change("dana@outside.example").status_code, 400)
        taken = self.change("omar@test.example")
        self.assertEqual(taken.status_code, 400)
        self.assertNotIn("omar", taken.get_json()["error"])          # does not say who has it
        self.assertEqual(self.dana.get("/api/me").get_json()["email"], "dana@test.example")


class VehicleRemovalWarning(AppTestCase):
    """P-03 (fixed in Week 12): the page warns before a car and its visits are removed."""

    def test_driver_page_asks_before_removing_a_car(self):
        """P-03: the remove button asks for confirmation and says what is deleted."""
        script = self.client().get("/app.js").get_data(as_text=True)
        self.assertIn("Its reservations and parking history will also be deleted", script)
        self.assertIn("window.confirm", script)


if __name__ == "__main__":
    unittest.main()
