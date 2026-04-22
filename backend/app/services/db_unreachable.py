"""Detect expected DB / TCP errors so resilient stores can log at debug instead of warning."""

from __future__ import annotations


def is_benign_database_unreachable(exc: BaseException) -> bool:
    """True when Postgres (or TCP) is simply not listening — not an app bug."""
    if isinstance(exc, ConnectionRefusedError):
        return True
    if isinstance(exc, TimeoutError):
        return True
    if isinstance(exc, OSError):
        errno = getattr(exc, "errno", None)
        if errno in (61, 111):  # macOS ECONNREFUSED; Linux often 111
            return True
    msg = str(exc).lower()
    if "connection refused" in msg:
        return True
    if "could not connect" in msg:
        return True
    if "errno 61" in msg or "errno 111" in msg:
        return True
    if "connect call failed" in msg and "refused" in msg:
        return True
    return False
