"""Start the Smart Parking server on https://localhost:5000.

The server only runs over HTTPS (SR-13). It uses the certificate created by
scripts/setup_dev.py. Flask's built-in server is fine for this prototype but
is not meant for production.

The cleanup job (PR-07 to PR-10) runs when the server starts and then once a day.
"""
import sys
from pathlib import Path

from werkzeug.serving import WSGIRequestHandler

from app import cleanup, create_app
from app.data_access.db import check_database_file

BASE_DIR = Path(__file__).resolve().parent
CERT_FILE = BASE_DIR / "certs" / "dev-cert.pem"
KEY_FILE = BASE_DIR / "certs" / "dev-key.pem"

# Hide the server software and Python version from response headers (SR-16).
WSGIRequestHandler.server_version = "SmartParking"
WSGIRequestHandler.sys_version = ""


def main():
    try:
        app = create_app()            # refuses to start without valid keys (SR-17, SR-18)
    except RuntimeError as error:
        sys.exit(str(error))
    if not (CERT_FILE.exists() and KEY_FILE.exists()):
        sys.exit("No TLS certificate found. Run: python scripts/setup_dev.py")
    try:
        check_database_file(app.config["DATABASE"])
    except RuntimeError as error:
        sys.exit(str(error))

    cleanup.start_daily(app)          # flow 9: now, then every 24 hours

    # debug=False: the debug page would show source code and let anyone run
    # commands on the server from the browser.
    app.run(host="127.0.0.1", port=5000, debug=False,
            ssl_context=(str(CERT_FILE), str(KEY_FILE)))


if __name__ == "__main__":
    main()
