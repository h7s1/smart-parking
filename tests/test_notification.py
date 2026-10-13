"""Reservation confirmation email, simulated (FR-08, flow 10)."""
import contextlib
import io
import unittest

from helpers import AppTestCase

from app.notification import console_sender, mask_email


class NotificationTests(AppTestCase):

    def setUp(self):
        super().setUp()
        self.dana = self.new_driver("dana@test.example")
        self.vehicle = self.add_vehicle(self.dana, "ABC1234")

    def test_email_sent_after_a_successful_reservation(self):
        """FR-08: to the driver, with the spot and times, and without the plate."""
        self.assertEqual(self.reserve(self.dana, self.vehicle).status_code, 201)
        self.assertEqual(len(self.sent_emails), 1)
        email = self.sent_emails[0]
        self.assertEqual(email["to"], "dana@test.example")
        self.assertIn("A-01", email["body"])
        self.assertIn("20/10/2026 10:00 UTC", email["body"])
        self.assertNotIn("ABC1234", email["body"])

    def test_no_email_when_the_reservation_fails(self):
        """Flow 10: sent only after a successful reservation."""
        self.assertEqual(self.reserve(self.dana, self.vehicle, spot_label="A-03").status_code, 409)
        self.assertEqual(self.reserve(self.dana, self.vehicle, start_in_hours=-1).status_code, 400)
        self.assertEqual(self.sent_emails, [])

    def test_a_failed_email_does_not_undo_the_reservation(self):
        def broken_sender(to, subject, body):
            raise ConnectionError("mail server down")
        self.app.config["EMAIL_SENDER"] = broken_sender
        with self.assertLogs(self.app.logger, level="WARNING") as logs:
            self.assertEqual(self.reserve(self.dana, self.vehicle).status_code, 201)
        self.assertEqual(len(self.query("SELECT id FROM reservations")), 1)
        self.assertNotIn("dana", "".join(logs.output))          # no personal data in the log

    def test_console_shows_only_part_of_the_address(self):
        """The simulated email in the server console hides most of the address."""
        self.assertEqual(mask_email("dana@test.example"), "d***@test.example")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            console_sender("dana@test.example", "Subject", "Body")
        self.assertIn("d***@test.example", output.getvalue())
        self.assertNotIn("dana@", output.getvalue())


if __name__ == "__main__":
    unittest.main()
