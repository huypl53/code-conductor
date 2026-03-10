"""State watcher — watches state.json for changes and broadcasts delta events.

Uses watchfiles.awatch on the parent directory (not the file directly) to
correctly detect atomic writes via os.replace which swaps inodes.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from watchfiles import awatch

from conductor.dashboard.events import classify_delta
from conductor.state.manager import StateManager
from conductor.state.models import ConductorState


async def state_watcher(
    state_path: Path,
    ws_manager: object,
    stop_event: asyncio.Event,
) -> None:
    """Watch state.json and broadcast delta events to connected WebSocket clients.

    Args:
        state_path: Absolute path to state.json.
        ws_manager: A ConnectionManager instance with a broadcast(message) method.
        stop_event: Set this event to stop watching.

    Notes:
        - Watches the parent directory (not state_path directly) because
          StateManager uses os.replace which swaps the inode — watching the
          file directly would miss events.
        - Reads state via asyncio.to_thread to avoid blocking the event loop.
        - Silently skips read errors (file may be mid-write during atomic swap).
    """
    prev: ConductorState | None = None

    async for changes in awatch(
        str(state_path.parent),
        stop_event=stop_event,
        debounce=200,
    ):
        # Filter: only process changes that involve state_path
        changed_names = {Path(path).name for _, path in changes}
        if state_path.name not in changed_names:
            continue

        try:
            new_state: ConductorState = await asyncio.to_thread(
                StateManager(state_path).read_state
            )
        except Exception:
            # State file may be mid-write; skip this change cycle
            continue

        events = classify_delta(prev, new_state)
        prev = new_state

        for event in events:
            await ws_manager.broadcast(event.model_dump_json())
