"""Pure helpers for registration identity handling.

Email addresses are treated case-insensitively for account lookup and for the
Firestore uniqueness index. Keep this module free of Streamlit and Firestore so
that its behaviour is covered by fast unit tests.
"""
from __future__ import annotations

import hashlib


def normalize_email(value: object) -> str | None:
    """Return the canonical form for comparison, or None for an empty value."""
    if not isinstance(value, str):
        return None
    normalized = value.strip().casefold()
    return normalized or None


def email_index_key(value: object) -> str | None:
    """Return a stable, Firestore-safe key for a canonical email address."""
    normalized = normalize_email(value)
    if normalized is None:
        return None
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
