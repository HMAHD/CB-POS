"""Validation helpers for CB POS."""

import re

_RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email(email: str | None) -> bool:
    """Return True if email matches a valid email address format."""
    if not email:
        return False
    return bool(_RE_EMAIL.match(email.strip()))
