"""Dashboard backend package — event classification for real-time state streaming."""
from conductor.dashboard.events import DeltaEvent, EventType, classify_delta

__all__ = ["DeltaEvent", "EventType", "classify_delta"]
