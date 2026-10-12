"""Time helpers. All times are handled and stored in UTC."""
from datetime import datetime, timezone

from flask import current_app

DB_FORMAT = "%Y-%m-%d %H:%M:%S"


def now():
    """The current UTC time, from the configured clock."""
    return current_app.config["CLOCK"]().replace(microsecond=0)


def to_db(moment):
    return moment.astimezone(timezone.utc).strftime(DB_FORMAT)


def from_db(text):
    return datetime.strptime(text, DB_FORMAT).replace(tzinfo=timezone.utc)


def db_to_api(text):
    """Convert a stored time to ISO 8601 in UTC, for example 2026-10-20T08:00:00Z."""
    return from_db(text).strftime("%Y-%m-%dT%H:%M:%SZ") if text else None
