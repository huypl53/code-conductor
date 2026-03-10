"""Dashboard backend package — event classification and real-time state streaming."""
from conductor.dashboard.events import DeltaEvent, EventType, classify_delta
from conductor.dashboard.server import ConnectionManager, create_app

__all__ = [
    "ConnectionManager",
    "DeltaEvent",
    "EventType",
    "classify_delta",
    "create_app",
]
