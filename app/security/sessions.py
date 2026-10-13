"""Login sessions kept on the server (FR-02, SR-03, SR-20, SR-21).

On login the server creates a random 256-bit token. The browser keeps the
token in a cookie; the database keeps only its SHA-256 hash.

Cookie settings:
  * HttpOnly: page scripts cannot read the cookie, so an injected script
    cannot steal it.
  * Secure: the cookie is only sent over HTTPS (SR-13).
  * SameSite=Strict: the browser does not send the cookie with requests that
    start on another website (protection against cross-site request forgery).

Because sessions live on the server, logging out really ends the session, and
a session ends after 30 minutes without activity.
"""
import hashlib
import secrets
from datetime import timedelta

from flask import current_app, request

from .. import clock
from ..data_access import sessions_repo

_MAX_TOKEN_LENGTH = 100


def _hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _cookie_name():
    return current_app.config["SESSION_COOKIE_NAME"]


def _token_from_request():
    token = request.cookies.get(_cookie_name())
    if not token or len(token) > _MAX_TOKEN_LENGTH:
        return None
    return token


def start(user_id):
    """Create a new session and return the token for the cookie."""
    token = secrets.token_urlsafe(32)
    sessions_repo.insert(_hash(token), user_id, clock.to_db(clock.now()))
    return token


def current_user():
    """Return {"id", "role"} for the request's session, or None.

    Ends the session if it has been idle for longer than SESSION_IDLE_MINUTES.
    """
    token = _token_from_request()
    if token is None:
        return None
    token_hash = _hash(token)
    row = sessions_repo.get_with_role(token_hash)
    if row is None:
        return None

    now = clock.now()
    idle_limit = timedelta(minutes=current_app.config["SESSION_IDLE_MINUTES"])
    if now - clock.from_db(row["last_seen_at"]) > idle_limit:
        sessions_repo.delete(token_hash)          # SR-21: idle timeout
        return None

    sessions_repo.touch(token_hash, clock.to_db(now))
    return {"id": row["user_id"], "role": row["role"]}


def end():
    """Delete the request's session on the server (SR-20: logout)."""
    token = _token_from_request()
    if token is not None:
        sessions_repo.delete(_hash(token))


def set_cookie(response, token):
    # No max_age: the server-side timeout decides how long a session lasts.
    response.set_cookie(
        _cookie_name(), token, httponly=True, secure=True, samesite="Strict", path="/"
    )


def clear_cookie(response):
    response.delete_cookie(
        _cookie_name(), path="/", httponly=True, secure=True, samesite="Strict"
    )
