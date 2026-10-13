"""Notification service (Figure 1, flow 10): the reservation confirmation email (FR-08).

The prototype does not send real email. The default sender prints a simulated
email to the server console, with most of the address hidden, and stores
nothing. A real system would pass the message to a mail server over TLS.

The message holds only the spot and the times. It has no license plate, and no
link or code that would let someone act on the reservation.
"""
from flask import current_app

from . import clock
from .data_access import users_repo
from .security import crypto

SUBJECT = "Your parking reservation is confirmed"


def mask_email(address):
    """d***@example.com: enough to see who it is for, without the full address."""
    local, _, domain = address.partition("@")
    return f"{local[:1]}***@{domain}"


def console_sender(to, subject, body):
    print(
        "----- Simulated email (FR-08) -----\n"
        f"To: {mask_email(to)}\n"
        f"Subject: {subject}\n\n"
        f"{body}\n"
        "-----------------------------------",
        flush=True,
    )


def _readable(api_time):
    return clock.from_db(api_time.replace("T", " ").rstrip("Z")).strftime("%d/%m/%Y %H:%M UTC")


def send_reservation_confirmation(driver_id, reservation):
    """Called only after the reservation has been saved. If sending fails, the
    reservation still stands; the failure is logged without any personal data."""
    try:
        user = users_repo.get(driver_id)
        to = crypto.decrypt(user["email_enc"], crypto.EMAIL)
        minutes = current_app.config["CANCEL_DEADLINE_MINUTES"]
        body = (
            f"Spot {reservation['spot']} is reserved for you "
            f"from {_readable(reservation['start'])} to {_readable(reservation['end'])}.\n"
            f"You can cancel it in the Smart Parking website up to {minutes} minutes "
            "before it starts."
        )
        sender = current_app.config["EMAIL_SENDER"] or console_sender
        sender(to, SUBJECT, body)
        return True
    except Exception:                                  # noqa: BLE001 - never break the reservation
        current_app.logger.warning("The reservation confirmation email could not be sent.")
        return False
