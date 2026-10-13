"""Checks that run before a protected API function (Figure 1: the API is the
single entry point, and the privilege boundary sits here).

  login_required     -> SR-03: a valid server-side session is required.
  roles_required     -> SR-04: the user's role is checked on the server before
                        the function runs.
  gate_key_required  -> SR-17: a gate event must carry the correct gate key.

Hiding a button in the web page is not access control: anyone can send a
request directly with a script. That is why every check happens here, on the
server. Every API function except register and login must use one of these
decorators; tests/test_authorization.py checks that none was forgotten.
"""
import hmac
from functools import wraps

from flask import current_app, g, jsonify, request

from ..security import sessions

GATE_KEY_HEADER = "X-Gate-Key"


def _not_logged_in():
    return jsonify(error="Please log in."), 401


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        user = sessions.current_user()
        if user is None:
            return _not_logged_in()
        g.user = user
        return view(*args, **kwargs)
    return wrapper


def roles_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            user = sessions.current_user()
            if user is None:
                return _not_logged_in()
            if user["role"] not in roles:
                return jsonify(error="You do not have permission to do this."), 403
            g.user = user
            return view(*args, **kwargs)
        return wrapper
    return decorator


def gate_key_required(view):
    """SR-17, TH-01: only the real gate (which knows the gate key) can send
    gate events. The key is compared in constant time, so the response time
    does not show how much of a guessed key was right."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        given = request.headers.get(GATE_KEY_HEADER, "").encode("utf-8")
        expected = current_app.config["GATE_KEY"].encode("utf-8")
        if not hmac.compare_digest(given, expected):
            current_app.logger.warning("A gate event was refused: missing or wrong gate key.")
            return jsonify(error="The gate key is missing or not valid."), 401
        return view(*args, **kwargs)
    return wrapper
