"""Application settings.

Secrets are never written in the source code. The encryption key and the gate
key are read from the environment (or a local .env file that is excluded from
Git) once, when the application starts (SR-20, SR-21).
"""
import base64
import os
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def utc_now():
    return datetime.now(timezone.utc)


class Config:
    DATABASE = str(BASE_DIR / "instance" / "smart_parking.db")

    # Set from SP_ENCRYPTION_KEY: 32 random bytes, base64-encoded (SR-21).
    ENCRYPTION_KEY = None

    # Set from SP_GATE_KEY: the shared secret the gate simulator sends with
    # every gate event (SR-20). At least 32 characters.
    GATE_KEY = None

    # SR-13: bcrypt work factor of at least 10. 12 is the default here.
    BCRYPT_ROUNDS = 12

    # SR-06: at least 8 characters (the team's decision in Week 8). NIST SP
    # 800-63B-4 asks for 15 when the password is the only factor; the team
    # accepted this (F-04, Week 11). Up to 64 characters.
    MIN_PASSWORD_LENGTH = 8
    MAX_PASSWORD_LENGTH = 64
    # Since Week 12, a new password is also checked against a list of common
    # and leaked passwords (app/security/password_blocklist.py), as NIST asks.

    # F-08 (fixed in Week 12): the car park is for the employees of the
    # companies in the business complex, so a driver must register with a work
    # email from one of these domains. The domains here are synthetic.
    ALLOWED_EMAIL_DOMAINS = ("smartparking.test",)

    # SR-02: block login for 15 minutes after 5 consecutive failed attempts.
    LOCKOUT_THRESHOLD = 5
    LOCKOUT_MINUTES = 15

    # SR-05: end a session after a time without activity. Admins and support
    # agents can see more data, so a computer left open is a bigger risk, and
    # their sessions end after 15 minutes (the NIST SP 800-63B-4 limit for AAL3).
    SESSION_IDLE_MINUTES = {"DRIVER": 30, "ADMIN": 15, "SUPPORT_AGENT": 15}
    # SR-23: end every session after a maximum length, even if it is still in
    # use. Roles with more privileges get shorter sessions: 4 hours is the
    # lower end of what OWASP suggests for an application used during a work day.
    SESSION_MAX_HOURS = {"DRIVER": 12, "ADMIN": 4, "SUPPORT_AGENT": 4}
    SESSION_COOKIE_NAME = "sp_session"

    # SR-22: reject a client after 60 requests in one minute.
    RATE_LIMIT_PER_MINUTE = 60

    # FR-07: a reservation can be cancelled up to 30 minutes before it starts.
    CANCEL_DEADLINE_MINUTES = 30

    # FR-06: one reservation lasts at most 24 hours.
    MAX_RESERVATION_HOURS = 24

    # Reject request bodies larger than 16 KB (input handling, SR-17).
    MAX_CONTENT_LENGTH = 16 * 1024

    # Retention periods from the Personal Data Map (PR-07 to PR-10).
    PARKING_SESSION_RETENTION_DAYS = 90      # PR-07, after the entry time
    RESERVATION_RETENTION_DAYS = 30          # PR-08, after the reservation ends
    DISPUTE_RETENTION_DAYS = 90              # PR-09, after the dispute is closed
    AUDIT_RETENTION_DAYS = 180               # PR-10, after the entry is created
    INACTIVE_ACCOUNT_DAYS = 365              # data map: 12 months without a login

    # The cleanup job runs when the server starts and then once a day (flow 9).
    CLEANUP_INTERVAL_HOURS = 24

    # FR-08: how the confirmation email is sent. The prototype only prints a
    # simulated email to the server console (see app/notification.py). Tests
    # replace it to check what would have been sent.
    EMAIL_SENDER = None

    # The clock is a setting so that tests can move time forward
    # (for example, to check that a 15-minute block ends).
    CLOCK = staticmethod(utc_now)


def load_env_file(path=BASE_DIR / ".env"):
    """Copy KEY=VALUE lines from a local .env file into the environment.

    Values that are already set in the environment are kept.
    """
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def settings_from_environment():
    load_env_file()
    settings = {
        "ENCRYPTION_KEY": os.environ.get("SP_ENCRYPTION_KEY"),
        "GATE_KEY": os.environ.get("SP_GATE_KEY"),
    }
    if os.environ.get("SP_DATABASE"):
        settings["DATABASE"] = os.environ["SP_DATABASE"]
    return settings


def check_settings(config):
    """Refuse to start with unsafe settings (fail securely)."""
    key = config.get("ENCRYPTION_KEY")
    if not key:
        raise RuntimeError(
            "SP_ENCRYPTION_KEY is not set. Run: python scripts/setup_dev.py"
        )
    try:
        raw = base64.b64decode(key, validate=True)
    except ValueError:
        raw = b""
    if len(raw) != 32:
        raise RuntimeError("SP_ENCRYPTION_KEY must be 32 bytes, base64-encoded.")
    if config.get("BCRYPT_ROUNDS", 0) < 10:
        raise RuntimeError("BCRYPT_ROUNDS must be at least 10 (SR-13).")
    gate_key = config.get("GATE_KEY")
    if not gate_key or len(gate_key) < 32:
        raise RuntimeError(
            "SP_GATE_KEY is not set or is too short. Run: python scripts/setup_dev.py"
        )
