"""One-time setup for a developer laptop.

1. Creates .env with a new random encryption key (SR-18). The .env file is
   listed in .gitignore, so the key never goes into the repository.
2. Creates a self-signed TLS certificate for https://localhost (SR-13).

Run from the project folder:  python scripts/setup_dev.py
"""
import base64
import ipaddress
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"
CERT_DIR = BASE_DIR / "certs"


def create_env_file():
    if ENV_FILE.exists():
        # Never replace an existing key: data encrypted with it could no longer be read.
        print(".env already exists; keeping the current key.")
        return
    key = base64.b64encode(os.urandom(32)).decode("ascii")
    ENV_FILE.write_text(
        "# Local secrets. Never commit this file.\n"
        f"SP_ENCRYPTION_KEY={key}\n",
        encoding="utf-8",
    )
    if os.name != "nt":
        ENV_FILE.chmod(0o600)        # readable by the owner only
    print("Created .env with a new encryption key.")


def create_dev_certificate():
    cert_file, key_file = CERT_DIR / "dev-cert.pem", CERT_DIR / "dev-key.pem"
    if cert_file.exists() and key_file.exists():
        print("TLS certificate already exists.")
        return
    CERT_DIR.mkdir(exist_ok=True)
    private_key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("localhost"),
                x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
            ]),
            critical=False,
        )
        .sign(private_key, hashes.SHA256())
    )
    key_file.write_bytes(private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    cert_file.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    if os.name != "nt":
        key_file.chmod(0o600)
    print("Created a self-signed TLS certificate for localhost in certs/.")


if __name__ == "__main__":
    create_env_file()
    create_dev_certificate()
    print("Next: python scripts/init_db.py")
    sys.exit(0)
