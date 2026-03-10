"""Custom exception hierarchy for conductor state operations."""
from __future__ import annotations


class StateError(Exception):
    """Base exception for all state operations."""


class StateLockTimeout(StateError):
    """Raised when filelock acquisition times out."""


class StateCorrupted(StateError):
    """Raised when state.json cannot be parsed or is invalid."""
