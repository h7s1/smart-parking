"""Gate simulator (Figure 1): pretends to be the camera at the parking gate.

It sends a license plate and a direction to the server over HTTPS, with the
gate key from .env (SR-20), and prints the answer (ALLOW or DENY) and how long
it took (NFR-02: at most 2 seconds).

Start the server first (python run.py), then in a second terminal:
    python scripts/gate_simulator.py entry ABC1234
    python scripts/gate_simulator.py exit ABC1234

To check that fake gates are refused (TH-01):
    python scripts/gate_simulator.py entry ABC1234 --no-key
    python scripts/gate_simulator.py entry ABC1234 --wrong-key
"""
import argparse
import json
import os
import secrets
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.config import load_env_file             # noqa: E402

# 127.0.0.1 rather than "localhost": on Windows, "localhost" is tried over IPv6
# first, and the failed attempt adds about 2 seconds before every request.
URL = "https://127.0.0.1:5000/api/gate/events"
CERT_FILE = BASE_DIR / "certs" / "dev-cert.pem"


def tls_context():
    """Trust only our own development certificate, and check it (SR-16)."""
    context = ssl.create_default_context(cafile=str(CERT_FILE))
    # The development certificate is self-signed and has no CA extensions,
    # which Python's strict mode would reject; every other check stays on.
    context.verify_flags &= ~getattr(ssl, "VERIFY_X509_STRICT", 0)
    return context


def main():
    parser = argparse.ArgumentParser(description="Send one gate event to the Smart Parking server.")
    parser.add_argument("direction", choices=["entry", "exit"])
    parser.add_argument("plate", help="license plate, for example ABC1234")
    key_options = parser.add_mutually_exclusive_group()
    key_options.add_argument("--no-key", action="store_true", help="send the event without a gate key")
    key_options.add_argument("--wrong-key", action="store_true", help="send a random, wrong gate key")
    args = parser.parse_args()

    load_env_file(BASE_DIR / ".env")
    headers = {"Content-Type": "application/json"}
    if args.wrong_key:
        headers["X-Gate-Key"] = secrets.token_urlsafe(32)
    elif not args.no_key:
        key = os.environ.get("SP_GATE_KEY")
        if not key:
            print("SP_GATE_KEY is not set. Run: python scripts/setup_dev.py")
            return 1
        headers["X-Gate-Key"] = key

    body = json.dumps({"direction": args.direction.upper(), "plate": args.plate}).encode("utf-8")
    request = urllib.request.Request(URL, data=body, headers=headers, method="POST")

    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, context=tls_context(), timeout=10) as response:
            status, answer = response.status, json.load(response)
    except urllib.error.HTTPError as error:
        status, answer = error.code, json.load(error)
    except urllib.error.URLError as error:
        print(f"Could not reach the server ({error.reason}). Is python run.py running?")
        return 1
    elapsed_ms = (time.perf_counter() - started) * 1000

    if status == 200:
        print(f"Gate decision: {answer['decision']}   ({elapsed_ms:.0f} ms)")
    else:
        print(f"Refused with status {status}: {answer.get('error')}   ({elapsed_ms:.0f} ms)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
