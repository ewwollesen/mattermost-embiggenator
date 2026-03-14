"""Utility functions for DN escaping and password hashing."""

from __future__ import annotations

import base64
import hashlib
import os


def hash_password(password: str, scheme: str = "{SSHA}") -> str:
    """Hash a password using the specified scheme.

    Supported schemes: {SSHA}, {SHA}, {PLAIN}

    Note: {SSHA} and {SHA} use SHA-1 as required by OpenLDAP's password
    storage format. SHA-1 is cryptographically weak — these hashes are
    intended for ephemeral test environments only, not production use.
    """
    scheme_upper = scheme.upper()

    if scheme_upper == "{SSHA}":
        salt = os.urandom(8)
        digest = hashlib.sha1(password.encode("utf-8") + salt).digest()
        return "{SSHA}" + base64.b64encode(digest + salt).decode("ascii")

    if scheme_upper == "{SHA}":
        digest = hashlib.sha1(password.encode("utf-8")).digest()
        return "{SHA}" + base64.b64encode(digest).decode("ascii")

    if scheme_upper == "{PLAIN}" or scheme_upper == "PLAIN":
        return password

    raise ValueError(f"Unsupported password scheme: {scheme}")


def needs_base64(value: str) -> bool:
    """Check if an LDIF attribute value needs base64 encoding (RFC 2849)."""
    if not value:
        return False
    # Must base64 encode if starts with space, colon, or '<'
    if value[0] in (" ", ":", "<"):
        return True
    # Must base64 encode if contains non-ASCII or control chars
    for ch in value:
        if ord(ch) > 126 or ord(ch) < 32:
            return True
    return False


def base64_encode_value(value: str) -> str:
    """Base64-encode a string value for LDIF output."""
    return base64.b64encode(value.encode("utf-8")).decode("ascii")
