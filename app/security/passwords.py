"""Password hashing with bcrypt (SR-13).

bcrypt adds a random salt to every password and is deliberately slow, which
makes guessing passwords from a stolen database expensive. The work factor
(BCRYPT_ROUNDS) is at least 10; the application refuses to start with less.
"""
import bcrypt
from flask import current_app


def hash_password(password):
    salt = bcrypt.gensalt(rounds=current_app.config["BCRYPT_ROUNDS"])
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("ascii")


def verify_password(password, password_hash):
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))


def spend_time_like_a_check(password):
    """Run one bcrypt check against a throwaway hash.

    Used when no account matches the email, or the account is blocked, so that a
    failed login takes about the same time in every case. Without this, a fast
    reply would reveal that an email is not registered.
    """
    dummy = current_app.extensions.get("dummy_password_hash")
    if dummy is None:
        dummy = hash_password("not-a-real-password-used-for-timing")
        current_app.extensions["dummy_password_hash"] = dummy
    verify_password(password, dummy)
