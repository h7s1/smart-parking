"""Blocklist check for new passwords (SR-06, added in Week 12 for F-04).

NIST SP 800-63B-4 asks for two things for passwords: a minimum length, and a
check of every new password against a list of commonly used, expected or
compromised values, including words from the context of the service and the
user's name. The team kept the 8-character minimum (F-04), so this check is
what stops the easiest passwords to guess, such as "password123".

A new password is refused when:
  * it is in common_passwords.txt, or becomes one of its values after
    removing numbers and symbols at the end ("welcome2026!") or after undoing
    simple letter swaps ("p@ssw0rd");
  * it is one character repeated ("aaaaaaaa") or a simple sequence ("23456789");
  * it contains the name of the service ("smartparking", "parking");
  * it contains the name part of the user's email (for dana.ali@..., "dana" or "ali").

The list is read once, when it is first needed.
"""
import re
from functools import lru_cache
from pathlib import Path

LIST_FILE = Path(__file__).with_name("common_passwords.txt")
SERVICE_WORDS = ("smartparking", "parking")
_SWAPS = str.maketrans({"@": "a", "4": "a", "0": "o", "1": "i", "!": "i",
                        "3": "e", "$": "s", "5": "s", "7": "t"})
_END_NUMBERS_AND_SYMBOLS = re.compile(r"[\d\W_]+$")
_EMAIL_NAME_PARTS = re.compile(r"[._+\-]")


@lru_cache(maxsize=1)
def _common_passwords():
    lines = LIST_FILE.read_text(encoding="utf-8").splitlines()
    return frozenset(line.strip() for line in lines if line.strip() and not line.startswith("#"))


def _forms(password):
    """The password in lower case, with letter swaps undone, and without
    numbers and symbols at the end."""
    lower = password.lower()
    forms = {lower, lower.translate(_SWAPS)}
    for value in list(forms):
        base = _END_NUMBERS_AND_SYMBOLS.sub("", value)
        if base:
            forms.add(base)
    return forms


def _is_sequence(text):
    steps = {ord(b) - ord(a) for a, b in zip(text, text[1:])}
    return len(steps) == 1 and steps <= {0, 1, -1}


def is_easy_to_guess(password, email=None):
    if _forms(password) & _common_passwords():
        return True
    if _is_sequence(password.lower()):
        return True
    compact = password.lower().replace(" ", "")
    if any(word in compact or word in compact.translate(_SWAPS) for word in SERVICE_WORDS):
        return True
    if email:
        name = email.split("@", 1)[0].lower()
        parts = [name] + _EMAIL_NAME_PARTS.split(name)
        if any(len(part) >= 3 and part in compact for part in parts):
            return True
    return False
