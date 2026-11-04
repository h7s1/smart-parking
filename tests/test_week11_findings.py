"""Week 11: tests for the review findings.

Most tests here validate an open or accepted finding: they show that it really
exists in the code (Table 23 for F-xx, Table 29 for P-xx in the report).
The session tests check the fix for F-05 (SR-23), which was added in Week 11.
All data is synthetic.
"""
import unittest

from helpers import ADMIN_EMAIL, SUPPORT_EMAIL, AppTestCase

from app import cleanup


class PasswordLengthFinding(AppTestCase):
    """F-04 (accepted): the minimum password length is 8 characters (SR-06)."""

    def test_eight_character_password_is_accepted(self):
        """F-04 confirmed: 8 characters are accepted and 7 are refused.

        NIST SP 800-63B-4 asks for at least 15 characters when the password is
        the only login factor. The team kept 8 for usability, with the lockout
        after 5 failed logins (SR-02) slowing password guessing.
        """
        self.assertEqual(self.register("dana@test.example", "eight888").status_code, 201)
        self.assertEqual(self.register("lama@test.example", "seven77").status_code, 400)


class MaximumSessionLength(AppTestCase):
    """F-05, fixed in Week 11 (SR-23). Before the fix, a session that was used at
    least every 30 minutes never ended, because there was only an idle timeout
    (SR-05). Now every session ends after 12 hours for drivers and 8 hours for
    admins and support agents, even if it is still in use.
    """

    STEP_MINUTES = 25          # shorter than the 30-minute idle timeout

    def assert_session_ends_after(self, browser, path, hours):
        elapsed = 0
        while elapsed + self.STEP_MINUTES <= hours * 60:
            self.clock.advance(minutes=self.STEP_MINUTES)
            elapsed += self.STEP_MINUTES
            self.assertEqual(browser.get(path).status_code, 200)    # still inside the limit
        self.clock.advance(minutes=self.STEP_MINUTES)                # now past the limit
        self.assertEqual(browser.get(path).status_code, 401)

    def test_driver_session_ends_after_12_hours(self):
        """SR-23 (negative): a driver's session in use for more than 12 hours ends."""
        driver = self.new_driver("dana@test.example")
        self.assert_session_ends_after(driver, "/api/me", hours=12)
        self.login("dana@test.example")                              # a new login works

    def test_admin_session_ends_after_8_hours(self):
        """SR-23 (negative): an admin's session in use for more than 8 hours ends."""
        admin = self.login(ADMIN_EMAIL)
        self.assert_session_ends_after(admin, "/api/admin/spots", hours=8)
        self.login(ADMIN_EMAIL)

    def test_support_agent_session_ends_after_8_hours(self):
        """SR-23 (negative): a support agent's session in use for more than 8 hours ends."""
        support = self.login(SUPPORT_EMAIL)
        self.assert_session_ends_after(support, "/api/support/disputes", hours=8)
        self.login(SUPPORT_EMAIL)

    def test_cleanup_removes_sessions_past_the_maximum_length(self):
        """SR-23: the cleanup job also deletes the rows of sessions that are too old."""
        driver = self.new_driver("dana@test.example")
        for _ in range(28):                       # used every 25 minutes for 11 h 40 min
            self.clock.advance(minutes=self.STEP_MINUTES)
            self.assertEqual(driver.get("/api/me").status_code, 200)
        self.clock.advance(minutes=self.STEP_MINUTES)   # 12 h 5 min old, but idle for only 25 minutes
        with self.app.app_context():
            cleanup.run()
        self.assertEqual(len(self.query("SELECT token_hash FROM login_sessions")), 0)


class RegistrationFinding(AppTestCase):
    """F-06 (accepted): registration shows whether an email is registered."""

    def test_registration_answer_differs_for_a_registered_email(self):
        """F-06 confirmed: a new email gets 201, a registered one gets 400.

        The message itself does not say why (SR-19), but the different answer
        is enough to learn that an account exists.
        """
        self.assertEqual(self.register("dana@test.example").status_code, 201)
        self.assertEqual(self.register("dana@test.example").status_code, 400)


class OpenRegistrationFinding(AppTestCase):
    """F-08 (new in Week 11, open): the car park is for the employees of the
    business complex (Introduction: Scope), but any email can register."""

    def test_any_email_can_register_as_a_driver(self):
        """F-08 confirmed: an email from outside the complex gets a driver account."""
        self.assertEqual(self.register("visitor@outside.example").status_code, 201)
        self.login("visitor@outside.example")


class DriverRightsFindings(AppTestCase):
    """P-02 and P-03 (open, Week 12): missing driver rights from the PDPL review."""

    def test_no_route_to_download_data_or_change_email_or_password(self):
        """P-02 and P-03 confirmed: the account routes are only register, login,
        logout, me and account deletion."""
        account_routes = {
            rule.rule for rule in self.app.url_map.iter_rules()
            if rule.rule.startswith(("/api/me", "/api/account", "/api/register",
                                     "/api/login", "/api/logout"))
        }
        self.assertEqual(account_routes, {"/api/register", "/api/login", "/api/logout",
                                          "/api/me", "/api/account/delete"})
        for rule in self.app.url_map.iter_rules():
            for word in ("export", "download", "password", "email"):
                self.assertNotIn(word, rule.rule)


if __name__ == "__main__":
    unittest.main()
