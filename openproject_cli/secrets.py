"""System keyring access for the API token, with graceful degradation.

The token is stored in the OS keyring (like ``gh``), keyed by the host URL so
several hosts can coexist. If no keyring backend is available (a common case on
headless servers and in CI), every call degrades quietly: reads return ``None``
and writes report failure, so the caller can fall back to the plain config file.
"""

from __future__ import annotations

KEYRING_SERVICE = "openproject-cli"


def get_token(url: str) -> str | None:
    """Return the stored token for ``url``, or None if absent/unavailable."""
    try:
        import keyring

        return keyring.get_password(KEYRING_SERVICE, url)
    except Exception:
        return None


def set_token(url: str, token: str) -> bool:
    """Store ``token`` for ``url`` in the keyring. Return True on success."""
    try:
        import keyring

        keyring.set_password(KEYRING_SERVICE, url, token)
        return True
    except Exception:
        return False


def delete_token(url: str) -> bool:
    """Remove the stored token for ``url``. Return True if one was deleted."""
    try:
        import keyring

        keyring.delete_password(KEYRING_SERVICE, url)
        return True
    except Exception:
        return False
