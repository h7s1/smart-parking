"""Audit logger (NFR-07, NFR-08, SR-08).

Records who did what, when and from which IP address. Users are recorded by ID
only, never by email or license plate (PR-06). The actions match the purposes
listed in the Personal Data Map: logins, failed logins, account creation and
deletion, dispute opening and closing, and every time a support agent opens a
driver's data, including refused attempts.
"""
import uuid

from flask import has_request_context, request

from .. import clock
from ..data_access import audit_repo

LOGIN_SUCCESS = "LOGIN_SUCCESS"
LOGIN_FAILED = "LOGIN_FAILED"
ACCOUNT_CREATED = "ACCOUNT_CREATED"
ACCOUNT_DELETED = "ACCOUNT_DELETED"
INACTIVE_ACCOUNT_DELETED = "INACTIVE_ACCOUNT_DELETED"    # by the cleanup job
DISPUTE_OPENED = "DISPUTE_OPENED"
DISPUTE_CLOSED = "DISPUTE_CLOSED"
SUPPORT_ACCESS = "SUPPORT_ACCESS"                        # NFR-08
SUPPORT_ACCESS_DENIED = "SUPPORT_ACCESS_DENIED"          # NFR-08, TH-09

ACTIONS = {
    LOGIN_SUCCESS, LOGIN_FAILED, ACCOUNT_CREATED, ACCOUNT_DELETED, INACTIVE_ACCOUNT_DELETED,
    DISPUTE_OPENED, DISPUTE_CLOSED, SUPPORT_ACCESS, SUPPORT_ACCESS_DENIED,
}


def record(action, user_id=None, target_id=None):
    """user_id: who acted. target_id: what the action was about."""
    if action not in ACTIONS:
        raise ValueError("Unknown audit action")
    ip_address = request.remote_addr if has_request_context() else None
    audit_repo.insert(
        str(uuid.uuid4()), user_id, action, target_id, ip_address, clock.to_db(clock.now())
    )
