"""Smart Parking System: application factory.

create_app() builds the Flask application and adds the protections that apply
to every request: request limits, JSON-only changes, safe error messages and
security headers.
"""
from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

from . import clock
from .api import bp as api_blueprint
from .config import Config, check_settings, settings_from_environment
from .data_access.db import close_db
from .errors import AppError
from .security import crypto
from .security.rate_limit import RateLimiter

# Messages for standard HTTP errors. None of them contain system details (SR-16).
_HTTP_MESSAGES = {
    400: "The request is not valid.",
    401: "Please log in.",
    403: "You do not have permission to do this.",
    404: "Not found.",
    405: "This action is not allowed here.",
    413: "The request is too large.",
    415: "Requests must be sent as JSON.",
    429: "Too many requests. Wait a minute and try again.",
}
_GENERIC_ERROR = "Something went wrong. Please try again later."


def _error(status, message):
    return jsonify(error=message), status


def create_app(test_config=None):
    app = Flask(__name__, static_folder="web", static_url_path="")
    app.config.from_object(Config)
    app.config.update(test_config if test_config is not None else settings_from_environment())
    check_settings(app.config)                  # refuses to start without a valid key (SR-18)

    crypto.init_app(app)
    limiter = RateLimiter(app.config["RATE_LIMIT_PER_MINUTE"])
    app.register_blueprint(api_blueprint)
    app.teardown_appcontext(close_db)

    @app.get("/")
    def index():
        return app.send_static_file("index.html")

    @app.before_request
    def protect_api():
        if not request.path.startswith("/api/"):
            return None
        # SR-19: request limit per client.
        if not limiter.allow(request.remote_addr or "unknown", clock.now()):
            return _error(429, _HTTP_MESSAGES[429])
        # SR-24: requests that change data must be JSON. A form on another
        # website cannot send JSON to this server, which, together with the
        # SameSite cookie, blocks cross-site request forgery.
        if request.method in ("POST", "PUT", "PATCH") and not request.is_json:
            return _error(415, _HTTP_MESSAGES[415])
        return None

    @app.after_request
    def security_headers(response):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; object-src 'none'; base-uri 'none'; "
            "frame-ancestors 'none'; form-action 'self'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"   # personal data is not cached
        if request.is_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"  # SR-13
        return response

    # SR-16: errors never show stack traces, SQL or personal data.
    @app.errorhandler(AppError)
    def handle_app_error(error):
        return _error(error.status, error.message)

    @app.errorhandler(HTTPException)
    def handle_http_error(error):
        return _error(error.code, _HTTP_MESSAGES.get(error.code, _GENERIC_ERROR))

    @app.errorhandler(Exception)
    def handle_unexpected_error(_error_):
        # The details go to the server console for the developers only.
        app.logger.exception("Unexpected error on %s %s", request.method, request.path)
        return _error(500, _GENERIC_ERROR)

    return app
