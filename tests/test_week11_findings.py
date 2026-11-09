"""Week 11: tests for the review findings.

Most tests here validate an open or accepted finding: they show that it really
exists in the code (Table 23 for F-xx, Table 29 for P-xx in the report). The
tests for F-08, P-02 and P-03 were changed in Week 12 into retests of the fixes.
The session tests check the fix for F-05 (SR-23) and the shorter idle timeout
for admins and support agents (SR-05), which were added in Week 11.
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
    (SR-05). Now every session ends after 12 hours for drivers and 4 hours for
    admins and support agents, even if it is still in use.
    """

    STEP_MINUTES = 25          # shorter than the drivers' 30-minute idle timeout

    def assert_session_ends_after(self, browser, path, hours, step):
        elapsed = 0
        while elapsed + step <= hours * 60:
            self.clock.advance(minutes=step)
            elapsed += step
            self.assertEqual(browser.get(path).status_code, 200)    # still inside the limit
        self.clock.advance(minutes=step)                             # now past the limit
        self.assertEqual(browser.get(path).status_code, 401)

    def test_driver_session_ends_after_12_hours(self):
        """SR-23 (negative): a driver's session in use for more than 12 hours ends."""
        driver = self.new_driver("dana@test.example")
        self.assert_session_ends_after(driver, "/api/me", hours=12, step=25)
        self.login("dana@test.example")                              # a new login works

    def test_admin_session_ends_after_4_hours(self):
        """SR-23 (negative): an admin's session in use for more than 4 hours ends."""
        admin = self.login(ADMIN_EMAIL)
        # used every 10 minutes, so the 15-minute idle timeout never ends it
        self.assert_session_ends_after(admin, "/api/admin/spots", hours=4, step=10)
        self.login(ADMIN_EMAIL)

    def test_support_agent_session_ends_after_4_hours(self):
        """SR-23 (negative): a support agent's session in use for more than 4 hours ends."""
        support = self.login(SUPPORT_EMAIL)
        self.assert_session_ends_after(support, "/api/support/disputes", hours=4, step=10)
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


class IdleTimeoutByRole(AppTestCase):
    """SR-05, changed in Week 11: admins and support agents can see more data,
    so their sessions end after 15 minutes without activity instead of 30. A
    computer left open can then be used by someone else for a shorter time."""

    def assert_idle_limit(self, browser, path):
        self.clock.advance(minutes=14)
        self.assertEqual(browser.get(path).status_code, 200)    # activity resets the timer
        self.clock.advance(minutes=16)
        self.assertEqual(browser.get(path).status_code, 401)    # 16 idle minutes: ended

    def test_admin_session_ends_after_15_idle_minutes(self):
        """SR-05 (negative): an admin's session ends after 15 minutes without activity."""
        self.assert_idle_limit(self.login(ADMIN_EMAIL), "/api/admin/spots")

    def test_support_agent_session_ends_after_15_idle_minutes(self):
        """SR-05 (negative): a support agent's session ends after 15 minutes without activity."""
        self.assert_idle_limit(self.login(SUPPORT_EMAIL), "/api/support/disputes")


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
    """F-08 (found in Week 11, fixed in Week 12): the car park is for the
    employees of the business complex (Introduction: Scope). In Week 11 this
    test showed that any email could register. The same test is now the
    retest: an email from outside the complex is refused."""

    def test_email_from_outside_the_complex_is_refused(self):
        """F-08 retest (negative): an email from outside the complex gets no account."""
        response = self.register("visitor@outside.example")
        self.assertEqual(response.status_code, 400)
        self.assertIn("work email", response.get_json()["error"])
        login = self.client().post("/api/login", json={"email": "visitor@outside.example",
                                                       "password": "correct horse battery staple"})
        self.assertEqual(login.status_code, 401)


class DriverRightsFindings(AppTestCase):
    """P-02 and P-03 (found in Week 10, fixed in Week 12): missing driver rights
    from the PDPL review. In Week 11 this test showed that the routes were
    missing. It is now the retest: the routes exist. What they do is tested in
    tests/test_week12_remediation.py."""

    def test_routes_to_download_data_and_change_email_and_password_exist(self):
        """P-02 and P-03 retest: the account routes now include export, email and password."""
        account_routes = {
            rule.rule for rule in self.app.url_map.iter_rules()
            if rule.rule.startswith(("/api/me", "/api/account", "/api/register",
                                     "/api/login", "/api/logout"))
        }
        self.assertEqual(account_routes, {"/api/register", "/api/login", "/api/logout",
                                          "/api/me", "/api/account/delete",
                                          "/api/account/export", "/api/account/email",
                                          "/api/account/password"})


if __name__ == "__main__":
    unittest.main()
