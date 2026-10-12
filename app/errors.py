"""Errors that can safely be shown to the user.

Every message here is written by us. Messages never repeat the user's input
and never contain system details or personal data (SR-16). Anything else that
goes wrong becomes a generic 500 error (see app/__init__.py).
"""


class AppError(Exception):
    status = 400
    message = "The request could not be completed."

    def __init__(self, message=None):
        super().__init__(message or self.message)
        if message:
            self.message = message


class ValidationError(AppError):
    """Invalid or incomplete input (NFR-04, SR-14)."""
    status = 400


class LoginFailed(AppError):
    """The same message for every failed login, so it does not reveal whether an
    email is registered or an account is blocked (SR-16)."""
    status = 401
    message = "Login failed. Check your email and password, or try again later."


class NotFound(AppError):
    """Also used when a record exists but belongs to someone else, so a driver
    cannot learn which IDs exist (SR-05)."""
    status = 404
    message = "Not found."


class Conflict(AppError):
    """A business rule stops the action (for example, an overlapping reservation)."""
    status = 409
