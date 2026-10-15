"""Input validation, SQL injection, error messages, request limits and settings
(SR-13, SR-17 to SR-22)."""
import ast
import base64
import importlib.util
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from helpers import GATE_KEY, PASSWORD, AppTestCase

from app import create_app
from app.data_access.db import check_database_file, connect, create_schema

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"

DATA_ACCESS_DIR = Path(__file__).resolve().parent.parent / "app" / "data_access"
LEAK_SIGNS = ("Traceback", "sqlite", "SELECT", 'File "', "Werkzeug", "line ")


class SqlInjectionTests(AppTestCase):
    """SR-17, SR-18, TH-02 (negative)."""

    def test_sql_injection_in_login_fails_safely(self):
        for attack in ("' OR '1'='1' --@x.test", "admin@test.example' --", "x@x.test'; DROP TABLE users; --"):
            response = self.client().post("/api/login", json={"email": attack, "password": "anything"})
            self.assertIn(response.status_code, (400, 401), attack)
        self.assertEqual(len(self.query("SELECT id FROM users")), 2)   # table intact, no login

    def test_sql_injection_in_plate_rejected(self):
        driver = self.new_driver("dana@test.example")
        response = driver.post("/api/vehicles", json={"plate": "ABC'); DROP TABLE vehicles; --"})
        self.assertEqual(response.status_code, 400)
        self.query("SELECT COUNT(*) FROM vehicles")                     # the table still exists

    def test_quotes_are_stored_as_data(self):
        """Input with SQL characters is saved as plain text, not run as SQL."""
        email = "o'brien--@test.example"
        self.assertEqual(self.register(email).status_code, 201)
        self.login(email)

    def test_data_access_code_never_builds_sql_from_strings(self):
        """SR-18: every execute() call gets fixed SQL text with ? placeholders,
        never an f-string or text joined with variables."""
        for source in DATA_ACCESS_DIR.glob("*.py"):
            tree = ast.parse(source.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "execute"):
                    sql = node.args[0]
                    fixed = isinstance(sql, ast.Constant) or (
                        isinstance(sql, ast.IfExp)
                        and isinstance(sql.body, ast.Constant) and isinstance(sql.orelse, ast.Constant))
                    self.assertTrue(fixed, f"{source.name} line {node.lineno}: SQL built from variables")


class ErrorMessageTests(AppTestCase):
    """SR-19 (negative): errors show no system details or personal data."""

    def assert_no_leak(self, response):
        body = response.get_data(as_text=True)
        for sign in LEAK_SIGNS:
            self.assertNotIn(sign, body)

    def test_malformed_json(self):
        response = self.client().post("/api/login", data="{not json", content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assert_no_leak(response)

    def test_unknown_route(self):
        response = self.client().get("/api/does-not-exist")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json(), {"error": "Not found."})

    def test_invalid_id_in_url(self):
        driver = self.new_driver("dana@test.example")
        response = driver.delete("/api/vehicles/1 OR 1=1")
        self.assertEqual(response.status_code, 404)
        self.assert_no_leak(response)

    def test_unexpected_error_gives_generic_message(self):
        def broken():
            raise RuntimeError("database password is hunter2")
        self.app.add_url_rule("/api/broken-for-test", view_func=broken)
        with self.assertLogs(self.app.logger, level="ERROR"):     # details go to the server log only
            response = self.client().get("/api/broken-for-test")
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("hunter2", response.get_data(as_text=True))
        self.assert_no_leak(response)

    def test_wrong_type_fields(self):
        response = self.client().post("/api/register", json={"email": ["a"], "password": {"x": 1}})
        self.assertEqual(response.status_code, 400)
        self.assert_no_leak(response)

    def test_request_too_large(self):
        response = self.client().post("/api/login", json={"email": "a" * 20_000, "password": "x"})
        self.assertEqual(response.status_code, 413)

    def test_password_longer_than_bcrypt_limit_does_not_crash(self):
        response = self.client().post("/api/login", json={"email": "a@test.example", "password": "x" * 80})
        self.assertEqual(response.status_code, 401)


class RequestProtectionTests(AppTestCase):

    def test_changes_must_be_sent_as_json(self):
        """Extra hardening (negative): a form posted from another website is refused."""
        response = self.client().post("/api/login", data={"email": "a@test.example", "password": PASSWORD})
        self.assertEqual(response.status_code, 415)

    def test_security_headers(self):
        response = self.client().get("/api/me")
        self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertIn("max-age", response.headers["Strict-Transport-Security"])


class RateLimitTests(AppTestCase):
    rate_limit = 60

    def test_more_than_60_requests_in_a_minute_rejected(self):
        """SR-22, TH-04 (negative)"""
        browser = self.client()
        for _ in range(60):
            self.assertEqual(browser.get("/api/me").status_code, 401)   # allowed (not logged in)
        self.assertEqual(browser.get("/api/me").status_code, 429)        # the 61st
        self.clock.advance(minutes=1)
        self.assertEqual(browser.get("/api/me").status_code, 401)        # allowed again


class SettingsTests(unittest.TestCase):

    def test_app_refuses_to_start_without_encryption_key(self):
        """SR-21: no key in the code means the app must be given one."""
        with self.assertRaises(RuntimeError):
            create_app({"DATABASE": ":memory:", "ENCRYPTION_KEY": None})

    def test_app_refuses_weak_bcrypt_setting(self):
        """SR-13"""
        key = base64.b64encode(os.urandom(32)).decode()
        with self.assertRaises(RuntimeError):
            create_app({"DATABASE": ":memory:", "ENCRYPTION_KEY": key, "BCRYPT_ROUNDS": 8,
                        "GATE_KEY": GATE_KEY})

    def test_app_refuses_to_start_without_a_strong_gate_key(self):
        """SR-20: the gate key comes from .env, never from the code."""
        key = base64.b64encode(os.urandom(32)).decode()
        for gate_key in (None, "", "short-key"):
            with self.assertRaises(RuntimeError):
                create_app({"DATABASE": ":memory:", "ENCRYPTION_KEY": key, "GATE_KEY": gate_key})

    def test_setup_adds_missing_gate_key_and_keeps_the_encryption_key(self):
        """SR-20, SR-21: running setup again never replaces a key."""
        spec = importlib.util.spec_from_file_location("setup_dev", SCRIPTS_DIR / "setup_dev.py")
        setup_dev = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(setup_dev)
        with tempfile.TemporaryDirectory() as folder:
            env_file = Path(folder) / ".env"
            env_file.write_text("SP_ENCRYPTION_KEY=old-key-stays\n", encoding="utf-8")
            setup_dev.ENV_FILE = env_file
            setup_dev.print = lambda *args, **kwargs: None
            setup_dev.create_env_file()
            setup_dev.create_env_file()                 # a second run changes nothing
            lines = env_file.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[0], "SP_ENCRYPTION_KEY=old-key-stays")
        self.assertEqual(len([line for line in lines if line.startswith("SP_GATE_KEY=")]), 1)
        self.assertGreaterEqual(len(lines[1].split("=", 1)[1]), 32)

    def test_old_database_is_refused_at_start_up(self):
        """A database made by the Week 8 code lacks new columns: start-up stops with a clear message."""
        with tempfile.TemporaryDirectory() as folder:
            old, new = os.path.join(folder, "old.db"), os.path.join(folder, "new.db")
            sqlite3.connect(old).close()
            conn = connect(new)
            create_schema(conn)
            conn.close()
            with self.assertRaisesRegex(RuntimeError, "--reset"):
                check_database_file(old)
            check_database_file(new)
            with self.assertRaisesRegex(RuntimeError, "init_db"):
                check_database_file(os.path.join(folder, "missing.db"))


if __name__ == "__main__":
    unittest.main()
