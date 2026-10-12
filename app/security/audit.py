"""Audit logger (NFR-07, SR-08).

Records who did what, when and from which IP address. Users are recorded by ID
only, never by email or license plate (PR-06). The actions match the purposes
listed in the Personal Data Map; dispute actions and support agent access
(NFR-08) will be added with the dispute functions in a later phase.
"""
import uuid

from flask import has_request_context, request

from .. import clock
from ..data_access import audit_repo

LOGIN_SUCCESS = "LOGIN_SUCCESS"
LOGIN_FAILED = "LOGIN_FAILED"
ACCOUNT_CREATED = "ACCOUNT_CREATED"
ACCOUNT_DELETED = "ACCOUNT_DELETED"

ACTIONS = {LOGIN_SUCCESS, LOGIN_FAILED, ACCOUNT_CREATED, ACCOUNT_DELETED}


def record(action, user_id=None, target_id=None):
    """user_id: who acted. target_id: what the action was about."""
    if action not in ACTIONS:
        raise ValueError("Unknown audit action")
    ip_address = request.remote_addr if has_request_context() else None
    audit_repo.insert(
        str(uuid.uuid4()), user_id, action, target_id, ip_address, clock.to_db(clock.now())
    )
