"""Start the Smart Parking server on https://localhost:5000.

The server only runs over HTTPS (SR-13). It uses the certificate created by
scripts/setup_dev.py. Flask's built-in server is fine for this prototype but
is not meant for production.
"""
import sys
from pathlib import Path

from werkzeug.serving import WSGIRequestHandler

from app import create_app

BASE_DIR = Path(__file__).resolve().parent
CERT_FILE = BASE_DIR / "certs" / "dev-cert.pem"
KEY_FILE = BASE_DIR / "certs" / "dev-key.pem"

# Hide the server software and Python version from response headers (SR-16).
WSGIRequestHandler.server_version = "SmartParking"
WSGIRequestHandler.sys_version = ""


def main():
    app = create_app()
    if not (CERT_FILE.exists() and KEY_FILE.exists()):
        sys.exit("No TLS certificate found. Run: python scripts/setup_dev.py")
    if not Path(app.config["DATABASE"]).exists():
        sys.exit("No database found. Run: python scripts/init_db.py")

    # debug=False: the debug page would show source code and let anyone run
    # commands on the server from the browser.
    app.run(host="127.0.0.1", port=5000, debug=False,
            ssl_context=(str(CERT_FILE), str(KEY_FILE)))


if __name__ == "__main__":
    main()
