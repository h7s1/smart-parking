"""Server-side input validation (SR-14, NFR-04).

Every value from the client is checked for type, length and format before it
reaches the business logic. Messages say what is wrong without repeating the
input (SR-16).
"""
import re
import uuid
from datetime import datetime, timezone

from flask import current_app, request

from ..errors import LoginFailed, NotFound, ValidationError

_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,189}\.[A-Za-z]{2,24}$")
_PLATE = re.compile(r"^[A-Z0-9]{2,10}$")
_BCRYPT_MAX_BYTES = 72        # bcrypt cannot use more than 72 bytes of a password


def json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValidationError("The request body must be a JSON object.")
    return data


def _text(data, field, label, max_length):
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{label} is required.")
    if len(value) > max_length:
        raise ValidationError(f"{label} is too long.")
    return value


def email(data):
    value = _text(data, "email", "Email", 254).strip().lower()
    if not _EMAIL.match(value):
        raise ValidationError("Enter a valid email address.")
    return value


def new_password(data):
    """Password rules for registration (SR-22)."""
    value = data.get("password")
    low = current_app.config["MIN_PASSWORD_LENGTH"]
    high = current_app.config["MAX_PASSWORD_LENGTH"]
    if (not isinstance(value, str) or not low <= len(value) <= high
            or len(value.encode("utf-8")) > _BCRYPT_MAX_BYTES):
        raise ValidationError(f"The password must be {low} to {high} characters.")
    return value


def login_details(data):
    """Login input. Missing fields get a clear message (NFR-04); anything else
    that is wrong gets the same message as a wrong password (SR-16)."""
    raw_email, password = data.get("email"), data.get("password")
    if not isinstance(raw_email, str) or not raw_email.strip() \
            or not isinstance(password, str) or not password:
        raise ValidationError("Enter your email and password.")
    value = raw_email.strip().lower()
    if len(value) > 254 or not _EMAIL.match(value) \
            or len(password.encode("utf-8")) > _BCRYPT_MAX_BYTES:
        raise LoginFailed()
    return value, password


def current_password(data):
    value = data.get("password")
    if not isinstance(value, str) or not value \
            or len(value.encode("utf-8")) > _BCRYPT_MAX_BYTES:
        raise ValidationError("Enter your password.")
    return value


def plate(data):
    """Upper case, without spaces or hyphens: "abc 1234" becomes "ABC1234"."""
    value = _text(data, "plate", "License plate", 20)
    value = value.upper().replace(" ", "").replace("-", "")
    if not _PLATE.match(value):
        raise ValidationError("A license plate must be 2 to 10 English letters and digits.")
    return value


def body_id(data, field, label):
    value = data.get(field)
    try:
        return str(uuid.UUID(value))
    except (TypeError, ValueError, AttributeError):
        raise ValidationError(f"{label} is not valid.")


def path_id(value):
    """An ID in the URL. An invalid ID is treated as a record that does not exist."""
    try:
        return str(uuid.UUID(value))
    except (TypeError, ValueError, AttributeError):
        raise NotFound()


def time(data, field, label):
    """ISO 8601 with a time zone, for example 2026-10-20T08:00:00Z."""
    value = data.get(field)
    try:
        if not isinstance(value, str) or len(value) > 40:
            raise ValueError
        moment = datetime.fromisoformat(value)
        if moment.tzinfo is None:
            raise ValueError
        return moment.astimezone(timezone.utc).replace(microsecond=0)
    except (ValueError, OverflowError):        # OverflowError: dates such as year 9999
        raise ValidationError(
            f"{label} must be a date and time with a time zone, for example 2026-10-20T08:00:00Z."
        )


def choice(data, field, label, allowed):
    value = data.get(field)
    if value not in allowed:
        raise ValidationError(f"{label} must be one of: {', '.join(allowed)}.")
    return value


def dispute_subject(data):
    """FR-15: a dispute is about exactly one reservation or one parking session.
    Returns (reservation_id, parking_session_id), one of them None."""
    has_reservation = data.get("reservation_id") is not None
    has_session = data.get("parking_session_id") is not None
    if has_reservation == has_session:
        raise ValidationError("Choose one reservation or one parking session.")
    if has_reservation:
        return body_id(data, "reservation_id", "Reservation"), None
    return None, body_id(data, "parking_session_id", "Parking session")
