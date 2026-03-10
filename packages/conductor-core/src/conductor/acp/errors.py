"""ACP exception hierarchy for Conductor communication layer."""


class ACPError(Exception):
    """Base exception for all ACP operations."""


class SessionError(ACPError):
    """Raised on session lifecycle failures (connect, disconnect, interrupt)."""


class PermissionTimeoutError(ACPError):
    """Raised when a permission callback exceeds the configured timeout.

    Informational — the handler returns PermissionResultDeny and callers may
    catch this to log or track timeout occurrences.
    """
