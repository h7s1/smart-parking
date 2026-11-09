"""Shared setup for the tests.

Each test gets its own temporary database, a new random encryption key and a
fake clock that the test can move forward. All data is synthetic.
"""
import base64
import os
import sqlite3
import sys
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flask.testing import FlaskClient                       # noqa: E402

from app import create_app                                  # noqa: E402
from app.data_access import spots_repo                      # noqa: E402
from app.data_access.db import connect, create_schema       # noqa: E402
from app.logic import accounts                              # noqa: E402

PASSWORD = "correct horse battery staple"        # 28 characters, synthetic
ADMIN_EMAIL = "admin@test.example"
SUPPORT_EMAIL = "support@test.example"
GATE_KEY = "test-gate-key-" + "x" * 30             # synthetic, test only


class HttpsTestClient(FlaskClient):
    """Sends every test request over HTTPS, like the real server (SR-16)."""

    def open(self, *args, **kwargs):
        kwargs.setdefault("base_url", "https://localhost")
        return super().open(*args, **kwargs)


class FakeClock:
    def __init__(self):
        self.current = datetime(2026, 10, 20, 8, 0, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.current

    def advance(self, **kwargs):
        self.current += timedelta(**kwargs)


def iso(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


class AppTestCase(unittest.TestCase):
    rate_limit = 10_000           # high, so only the rate-limit test is limited

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmp.name, "test.db")
        self.clock = FakeClock()
        self.sent_emails = []                      # FR-08: what would have been sent
        self.app = create_app({
            "DATABASE": self.db_path,
            "ENCRYPTION_KEY": base64.b64encode(os.urandom(32)).decode("ascii"),
            "GATE_KEY": GATE_KEY,
            "BCRYPT_ROUNDS": 10,                   # the minimum SR-13 allows
            "CLOCK": self.clock,
            "RATE_LIMIT_PER_MINUTE": self.rate_limit,
            "ALLOWED_EMAIL_DOMAINS": ("test.example",),   # F-08: the synthetic work domain in tests
            "EMAIL_SENDER": lambda to, subject, body: self.sent_emails.append(
                {"to": to, "subject": subject, "body": body}),
        })
        self.app.test_client_class = HttpsTestClient
        conn = connect(self.db_path)
        create_schema(conn)
        conn.close()

        with self.app.app_context():
            self.spot_ids = {}
            for label, status in (("A-01", "FREE"), ("A-02", "FREE"), ("A-03", "DISABLED")):
                spot_id = str(uuid.uuid4())
                spots_repo.insert(spot_id, label, status)
                self.spot_ids[label] = spot_id
            accounts.create_staff_account(ADMIN_EMAIL, PASSWORD, accounts.ADMIN)
            accounts.create_staff_account(SUPPORT_EMAIL, PASSWORD, accounts.SUPPORT_AGENT)

    def tearDown(self):
        self._tmp.cleanup()

    # ----- helpers -----

    def client(self):
        """A new browser with no cookies."""
        return self.app.test_client()

    def register(self, email, password=PASSWORD):
        return self.client().post("/api/register", json={"email": email, "password": password})

    def login(self, email, password=PASSWORD):
        c = self.client()
        response = c.post("/api/login", json={"email": email, "password": password})
        self.assertEqual(response.status_code, 200, response.get_json())
        return c

    def new_driver(self, email):
        self.assertEqual(self.register(email).status_code, 201)
        return self.login(email)

    def add_vehicle(self, client, plate):
        response = client.post("/api/vehicles", json={"plate": plate})
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()["vehicle"]["id"]

    def reserve(self, client, vehicle_id, spot_label="A-01", start_in_hours=2, hours=1):
        start = self.clock() + timedelta(hours=start_in_hours)
        return client.post("/api/reservations", json={
            "vehicle_id": vehicle_id,
            "spot_id": self.spot_ids[spot_label],
            "start": iso(start),
            "end": iso(start + timedelta(hours=hours)),
        })

    def gate(self, plate, direction="ENTRY", key=GATE_KEY):
        """Send one gate event, as the gate simulator does."""
        headers = {} if key is None else {"X-Gate-Key": key}
        return self.client().post("/api/gate/events", headers=headers,
                                  json={"plate": plate, "direction": direction})

    def decision(self, plate, direction="ENTRY"):
        response = self.gate(plate, direction)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()["decision"]

    def query(self, sql, params=()):
        """Read the database directly, as an attacker with a stolen copy would."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def audit_actions(self):
        return [row["action"] for row in self.query("SELECT action FROM audit_log")]
