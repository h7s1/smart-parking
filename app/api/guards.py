"""Checks that run before a protected API function (Figure 1: the API is the
single entry point, and the privilege boundary sits here).

  login_required  -> SR-03: a valid server-side session is required.
  roles_required  -> SR-04: the user's role is checked on the server before the
                     function runs.

Hiding a button in the web page is not access control: anyone can send a
request directly with a script. That is why every check happens here, on the
server. Every API function except register and login must use one of these
decorators; tests/test_authorization.py checks that none was forgotten.
"""
from functools import wraps

from flask import g, jsonify

from ..security import sessions


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
