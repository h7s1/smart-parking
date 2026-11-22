"""API layer (Figure 3): the single entry point for the web pages and the gate.

Each route: checks the session and role, or the gate key (guards.py),
validates the input (validation.py), then calls the business logic.
"""
from flask import Blueprint

bp = Blueprint("api", __name__, url_prefix="/api")

# Imported after bp exists, because the route modules attach their routes to it.
from . import (admin_routes, auth_routes, dispute_routes, gate_routes,  # noqa: E402,F401
               reservation_routes, support_routes, vehicle_routes)
