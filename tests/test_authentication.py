"""Authentication, passwords, sessions and accounts."""
import unittest

from helpers import ADMIN_EMAIL, PASSWORD, AppTestCase


class RegistrationTests(AppTestCase):

    def test_register_creates_driver_account(self):
        """FR-01"""
        self.assertEqual(self.register("dana@test.example").status_code, 201)
        me = self.login("dana@test.example").get("/api/me").get_json()
        self.assertEqual(me["role"], "DRIVER")

    def test_register_cannot_choose_admin_role(self):
        """FR-01, TH-10 (negative): a role sent in the request is ignored."""
        response = self.client().post("/api/register", json={
            "email": "mallory@test.example", "password": PASSWORD, "role": "ADMIN"})
        self.assertEqual(response.status_code, 201)
        me = self.login("mallory@test.example").get("/api/me").get_json()
        self.assertEqual(me["role"], "DRIVER")

    def test_register_rejects_invalid_input(self):
        """NFR-04, SR-14 (negative)"""
        bad_email = self.register("not-an-email")
        self.assertEqual(bad_email.status_code, 400)
        self.assertEqual(bad_email.get_json()["error"], "Enter a valid email address.")
        short_password = self.register("dana@test.example", "short")
        self.assertEqual(short_password.status_code, 400)
        self.assertIn("15 to 64 characters", short_password.get_json()["error"])

    def test_duplicate_email_message_does_not_confirm_account(self):
        """SR-16 (negative): the message does not say the email is registered."""
        self.register("dana@test.example")
        response = self.register("dana@test.example")
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("dana", response.get_data(as_text=True))
        self.assertNotIn("already registered", response.get_data(as_text=True))

    def test_password_stored_only_as_bcrypt_hash(self):
        """SR-10: salted bcrypt hash with a work factor of at least 10."""
        self.register("dana@test.example")
        for row in self.query("SELECT password_hash FROM users"):
            stored = row["password_hash"]
            self.assertNotIn(PASSWORD, stored)
            self.assertTrue(stored.startswith("$2b$"))
            self.assertGreaterEqual(int(stored[4:6]), 10)

    def test_email_stored_only_encrypted(self):
        """PR-03: a stolen copy of the database does not show emails."""
        self.register("dana@test.example")
        dump = " ".join(row["email_enc"] for row in self.query("SELECT email_enc FROM users"))
        self.assertNotIn("dana", dump)
        self.assertNotIn("@", dump)


class LoginTests(AppTestCase):

    def setUp(self):
        super().setUp()
        self.register("dana@test.example")

    def test_login_sets_protected_session_cookie(self):
        """FR-02, SR-13: HttpOnly, Secure and SameSite=Strict."""
        response = self.client().post("/api/login", json={
            "email": "dana@test.example", "password": PASSWORD})
        self.assertEqual(response.status_code, 200)
        cookie = response.headers["Set-Cookie"]
        for flag in ("HttpOnly", "Secure", "SameSite=Strict"):
            self.assertIn(flag, cookie)

    def test_login_email_is_case_insensitive(self):
        self.login("Dana@Test.Example")

    def test_failed_login_message_is_the_same_for_unknown_email(self):
        """SR-16 (negative): no hint about which emails are registered."""
        wrong_password = self.client().post("/api/login", json={
            "email": "dana@test.example", "password": "wrong password here!!"})
        unknown_email = self.client().post("/api/login", json={
            "email": "nobody@test.example", "password": "wrong password here!!"})
        self.assertEqual(wrong_password.status_code, 401)
        self.assertEqual(unknown_email.status_code, 401)
        self.assertEqual(wrong_password.get_json(), unknown_email.get_json())

    def test_account_blocked_for_15_minutes_after_5_failures(self):
        """SR-02 (negative)"""
        attacker = self.client()
        for _ in range(5):
            attacker.post("/api/login", json={"email": "dana@test.example", "password": "guess guess guess!"})

        # Even the correct password is refused during the block, with the same message.
        blocked = self.client().post("/api/login", json={"email": "dana@test.example", "password": PASSWORD})
        self.assertEqual(blocked.status_code, 401)

        self.clock.advance(minutes=14)
        self.assertEqual(self.client().post("/api/login", json={
            "email": "dana@test.example", "password": PASSWORD}).status_code, 401)

        self.clock.advance(minutes=1, seconds=1)
        self.login("dana@test.example")

    def test_four_failures_do_not_block(self):
        """SR-02: only 5 consecutive failures block the account."""
        for _ in range(4):
            self.client().post("/api/login", json={"email": "dana@test.example", "password": "guess guess guess!"})
        self.login("dana@test.example")


class SessionTests(AppTestCase):

    def setUp(self):
        super().setUp()
        self.register("dana@test.example")
        self.browser = self.login("dana@test.example")

    def test_functions_require_login(self):
        """SR-03 (negative)"""
        stranger = self.client()
        for path in ("/api/me", "/api/vehicles", "/api/reservations", "/api/admin/audit-log"):
            self.assertEqual(stranger.get(path).status_code, 401, path)

    def test_logout_ends_session_on_server(self):
        """PROPOSED-1 (negative): an old cookie is useless after logout."""
        token = self.browser.get_cookie("sp_session").value
        self.assertEqual(self.browser.post("/api/logout", json={}).status_code, 200)

        replay = self.client()
        replay.set_cookie("sp_session", token)
        self.assertEqual(replay.get("/api/me").status_code, 401)

    def test_session_ends_after_30_idle_minutes(self):
        """PROPOSED-2"""
        self.clock.advance(minutes=29)
        self.assertEqual(self.browser.get("/api/me").status_code, 200)   # activity resets the timer
        self.clock.advance(minutes=29)
        self.assertEqual(self.browser.get("/api/me").status_code, 200)
        self.clock.advance(minutes=31)
        self.assertEqual(self.browser.get("/api/me").status_code, 401)

    def test_session_token_not_stored_in_plain_form(self):
        """A stolen copy of the sessions table cannot be used to log in."""
        token = self.browser.get_cookie("sp_session").value
        stored = [row["token_hash"] for row in self.query("SELECT token_hash FROM login_sessions")]
        self.assertNotIn(token, stored)

    def test_forged_cookie_rejected(self):
        """SR-03 (negative)"""
        forger = self.client()
        forger.set_cookie("sp_session", "made-up-token-value")
        self.assertEqual(forger.get("/api/me").status_code, 401)


class AuditAndDeletionTests(AppTestCase):

    def test_logins_and_account_creation_recorded(self):
        """NFR-07, SR-08"""
        self.register("dana@test.example")
        self.login("dana@test.example")
        self.client().post("/api/login", json={"email": "dana@test.example", "password": "wrong password here!!"})
        actions = self.audit_actions()
        for action in ("ACCOUNT_CREATED", "LOGIN_SUCCESS", "LOGIN_FAILED"):
            self.assertIn(action, actions)

    def test_malformed_login_attempt_recorded(self):
        """NFR-07: a login with a malformed email is still recorded as a failure."""
        before = self.audit_actions().count("LOGIN_FAILED")
        response = self.client().post("/api/login", json={"email": "not-an-email", "password": "anything"})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.audit_actions().count("LOGIN_FAILED"), before + 1)

    def test_audit_log_holds_ids_not_emails(self):
        """PR-06"""
        self.register("dana@test.example")
        self.login("dana@test.example")
        self.client().post("/api/login", json={"email": "ghost@test.example", "password": "wrong password here!!"})
        for row in self.query("SELECT * FROM audit_log"):
            self.assertNotIn("@", " ".join(str(value) for value in tuple(row)))

    def test_audit_entries_cannot_be_changed_or_deleted_early(self):
        """PROPOSED-3 (negative): blocked inside the database itself."""
        import sqlite3
        self.register("dana@test.example")
        conn = sqlite3.connect(self.db_path)
        try:
            with self.assertRaises(sqlite3.DatabaseError):
                conn.execute("UPDATE audit_log SET action = 'NOTHING'")
            with self.assertRaises(sqlite3.DatabaseError):
                conn.execute("DELETE FROM audit_log")
        finally:
            conn.close()

    def test_delete_account_removes_personal_data(self):
        """FR-03, PR-11"""
        driver = self.new_driver("dana@test.example")
        vehicle_id = self.add_vehicle(driver, "ABC1234")
        self.assertEqual(self.reserve(driver, vehicle_id).status_code, 201)

        response = driver.post("/api/account/delete", json={"password": PASSWORD})
        self.assertEqual(response.status_code, 200)

        for table in ("users", "vehicles", "reservations", "login_sessions"):
            count = self.query(f"SELECT COUNT(*) AS n FROM {table}")[0]["n"]
            expected = 2 if table == "users" else 0          # the admin and support agent remain
            self.assertEqual(count, expected, table)
        self.assertIn("ACCOUNT_DELETED", self.audit_actions())
        self.assertEqual(driver.get("/api/me").status_code, 401)

    def test_delete_account_needs_the_password(self):
        """FR-03 (negative)"""
        driver = self.new_driver("dana@test.example")
        response = driver.post("/api/account/delete", json={"password": "not my password at all"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(driver.get("/api/me").status_code, 200)

    def test_staff_cannot_use_driver_account_deletion(self):
        """SR-04 (negative)"""
        admin = self.login(ADMIN_EMAIL)
        self.assertEqual(admin.post("/api/account/delete", json={"password": PASSWORD}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
