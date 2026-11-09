"""Account routes: register, log in, log out, profile, change password and
email, download my data, delete account."""
from flask import g, jsonify

from . import bp, validation
from .guards import login_required, roles_required
from ..errors import LoginFailed
from ..logic import accounts, my_data
from ..security import sessions


@bp.post("/register")
def register():
    """FR-01. Public: no login needed."""
    data = validation.json_body()
    email = validation.email(data)
    password = validation.new_password(data, email=email)
    accounts.register_driver(email, password)
    return jsonify(message="Account created. You can now log in."), 201


@bp.post("/login")
def login():
    """SR-01, FR-02. Public: no login needed."""
    data = validation.json_body()
    try:
        email, password = validation.login_details(data)
    except LoginFailed:
        accounts.record_rejected_login()     # NFR-07: malformed attempts are recorded too
        raise
    user_id, role = accounts.log_in(email, password)

    # Drop any session this browser already had and issue a new token, so a
    # token planted before login cannot be reused (session fixation).
    sessions.end()
    token = sessions.start(user_id)

    response = jsonify(message="Logged in.", role=role)
    sessions.set_cookie(response, token)
    return response


@bp.post("/logout")
@login_required
def logout():
    """SR-04: logging out ends the session on the server."""
    sessions.end()
    response = jsonify(message="Logged out.")
    sessions.clear_cookie(response)
    return response


@bp.get("/me")
@login_required
def me():
    return jsonify(accounts.profile(g.user["id"]))


@bp.post("/account/delete")
@roles_required(accounts.DRIVER)
def delete_account():
    """FR-03, PR-11."""
    password = validation.current_password(validation.json_body())
    accounts.delete_driver_account(g.user["id"], password)
    response = jsonify(message="Your account and its data have been deleted.")
    sessions.clear_cookie(response)
    return response


@bp.post("/account/password")
@roles_required(accounts.DRIVER)
def change_password():
    """P-03, SR-06. Ends the driver's other sessions."""
    data = validation.json_body()
    current = validation.current_password(data, "current_password")
    email = accounts.profile(g.user["id"])["email"]
    new = validation.new_password(data, "new_password", email=email)
    accounts.change_password(g.user["id"], current, new)
    sessions.end_other_sessions(g.user["id"])
    return jsonify(message="Your password has been changed. You were logged out on other devices.")


@bp.post("/account/email")
@roles_required(accounts.DRIVER)
def change_email():
    """P-03, F-08."""
    data = validation.json_body()
    password = validation.current_password(data)
    email = validation.email(data)
    accounts.change_email(g.user["id"], password, email)
    return jsonify(message="Your email has been changed.", email=email)


@bp.post("/account/export")
@roles_required(accounts.DRIVER)
def export_my_data():
    """P-02: a copy of the driver's own data, as a JSON file."""
    password = validation.current_password(validation.json_body())
    response = jsonify(my_data.export_driver_data(g.user["id"], password))
    response.headers["Content-Disposition"] = 'attachment; filename="my-smart-parking-data.json"'
    response.headers["Cache-Control"] = "no-store"
    return response
