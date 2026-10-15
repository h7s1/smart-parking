"""Accounts: registration, login and account deletion."""
import uuid
from datetime import timedelta

from flask import current_app

from .. import clock
from ..data_access import parking_sessions_repo, users_repo
from ..data_access.db import transaction
from ..errors import Conflict, LoginFailed, ValidationError
from ..security import audit, crypto, passwords

DRIVER = "DRIVER"
ADMIN = "ADMIN"
SUPPORT_AGENT = "SUPPORT_AGENT"

REGISTRATION_FAILED = "The account could not be created. If you already have one, log in instead."


def _find_user_id(email):
    """Find a user by decrypting each stored email and comparing (team design).

    Known limitation: this reads every user on each lookup. A larger system
    would store a keyed hash of the email and search by that instead.
    """
    for row in users_repo.list_email_ciphertexts():
        if crypto.decrypt(row["email_enc"], crypto.EMAIL) == email:
            return row["id"]
    return None


def _create_user(email, password, role):
    password_hash = passwords.hash_password(password)   # slow, so done before locking
    user_id = str(uuid.uuid4())                         # random UUID (SR-10)
    # One transaction with the write lock taken first, so two requests cannot
    # register the same email at the same moment.
    with transaction(immediate=True):
        if _find_user_id(email) is not None:
            # The message does not say that the email is registered (SR-19).
            # Known limitation: the failed status still shows it, so the request
            # limit (SR-22) is what slows down mass checking. A full fix needs
            # email verification, which is out of scope.
            raise ValidationError(REGISTRATION_FAILED)
        users_repo.insert(
            user_id,
            crypto.encrypt(email, crypto.EMAIL),          # PR-03
            password_hash,                                # SR-13
            role,
            clock.to_db(clock.now()),
        )
        audit.record(audit.ACCOUNT_CREATED, user_id=user_id, target_id=user_id)  # SR-11
    return user_id


def register_driver(email, password):
    """FR-01: public registration always creates a DRIVER account.

    The role is never read from the request, so nobody can register as an admin.
    """
    return _create_user(email, password, DRIVER)


def create_staff_account(email, password, role):
    """Admin and support agent accounts are created by the setup script only,
    never through the public API."""
    if role not in (ADMIN, SUPPORT_AGENT):
        raise ValueError("Staff role must be ADMIN or SUPPORT_AGENT")
    return _create_user(email, password, role)


def log_in(email, password):
    """SR-01, SR-02. Returns (user_id, role) or raises LoginFailed.

    Every failure raises the same LoginFailed message (SR-19).
    """
    config = current_app.config
    now = clock.now()

    user_id = _find_user_id(email)
    if user_id is None:
        passwords.spend_time_like_a_check(password)
        audit.record(audit.LOGIN_FAILED)          # no email is stored (PR-06)
        raise LoginFailed()

    user = users_repo.get(user_id)

    # SR-02: while the account is blocked, the password is not checked at all,
    # so password guessing cannot continue during the block.
    if user["locked_until"] and clock.from_db(user["locked_until"]) > now:
        passwords.spend_time_like_a_check(password)
        audit.record(audit.LOGIN_FAILED, target_id=user_id)
        raise LoginFailed()

    if not passwords.verify_password(password, user["password_hash"]):
        failures = user["failed_logins"] + 1
        locked_until = None
        if failures >= config["LOCKOUT_THRESHOLD"]:
            locked_until = clock.to_db(now + timedelta(minutes=config["LOCKOUT_MINUTES"]))
            failures = 0
        users_repo.set_failed_logins(user_id, failures, locked_until)
        audit.record(audit.LOGIN_FAILED, target_id=user_id)     # NFR-07
        raise LoginFailed()

    users_repo.record_successful_login(user_id, clock.to_db(now))
    audit.record(audit.LOGIN_SUCCESS, user_id=user_id)          # NFR-07
    return user_id, user["role"]


def record_rejected_login():
    """A login attempt rejected before any account lookup (for example, a
    malformed email). Recorded without the email (PR-06)."""
    audit.record(audit.LOGIN_FAILED)


def profile(user_id):
    """The logged-in user's own email and role. The user ID is not shown
    (Personal Data Map: not shown to drivers)."""
    user = users_repo.get(user_id)
    return {"email": crypto.decrypt(user["email_enc"], crypto.EMAIL), "role": user["role"]}


def delete_driver_account(user_id, password):
    """FR-03, PR-11: delete the driver and all their personal data.

    The password is asked again, so someone who finds an open session on a
    shared computer cannot delete the account.
    """
    user = users_repo.get(user_id)
    if user is None or not passwords.verify_password(password, user["password_hash"]):
        raise ValidationError("The password is not correct.")
    with transaction(immediate=True):
        if parking_sessions_repo.owner_has_open_session(user_id):
            # Deleting now would leave the spot OCCUPIED with no session behind it.
            raise Conflict("The account cannot be deleted while one of your vehicles is parked.")
        users_repo.delete(user_id)      # cascades to vehicles, reservations, sessions, disputes
        audit.record(audit.ACCOUNT_DELETED, user_id=user_id, target_id=user_id)  # SR-11
