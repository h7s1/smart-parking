"""Encryption service for emails and license plates (PR-03, PR-04).

Algorithm: AES-256-GCM, from the "cryptography" library.
  * The 32-byte key comes from SP_ENCRYPTION_KEY and is read once, when the
    application starts. It is never stored in the code or the database (SR-21).
  * Each value gets a new random 12-byte nonce, so the same email encrypted
    twice gives two different results.
  * GCM also checks integrity: a changed ciphertext fails to decrypt.
  * The purpose ("email" or "plate") is bound to the ciphertext, so an
    encrypted plate copied into the email column will not decrypt.
"""
import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from flask import current_app

EMAIL = b"email"
PLATE = b"plate"
_NONCE_SIZE = 12


def init_app(app):
    key = base64.b64decode(app.config["ENCRYPTION_KEY"])
    app.extensions["aesgcm"] = AESGCM(key)


def _cipher():
    return current_app.extensions["aesgcm"]


def encrypt(text, purpose):
    nonce = os.urandom(_NONCE_SIZE)
    ciphertext = _cipher().encrypt(nonce, text.encode("utf-8"), purpose)
    return base64.b64encode(nonce + ciphertext).decode("ascii")


def decrypt(token, purpose):
    raw = base64.b64decode(token)
    nonce, ciphertext = raw[:_NONCE_SIZE], raw[_NONCE_SIZE:]
    return _cipher().decrypt(nonce, ciphertext, purpose).decode("utf-8")
