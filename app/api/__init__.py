"""API layer (Figure 1): the single entry point for the web pages.

Each route: checks the session and role (guards.py), validates the input
(validation.py), then calls the business logic.
"""
from flask import Blueprint

bp = Blueprint("api", __name__, url_prefix="/api")

# Imported after bp exists, because the route modules attach their routes to it.
from . import admin_routes, auth_routes, reservation_routes, vehicle_routes  # noqa: E402,F401
