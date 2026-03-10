"""SessionRegistry — maps agent IDs to SDK session IDs for restart recovery.

Persists to .conductor/sessions.json alongside state.json.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import filelock


class SessionRegistry:
    """Maps agent IDs to SDK session IDs for restart recovery.

    Persists to .conductor/sessions.json alongside state.json.
    Atomic writes prevent corruption on crash.

    Usage::

        registry = SessionRegistry()
        registry.register("agent-001", "sess-abc")
        session_id = registry.get("agent-001")  # "sess-abc"

        # Persist to disk
        path = Path(".conductor/sessions.json")
        registry.save(path)

        # Load on restart
        registry = SessionRegistry.load(path)
        session_id = registry.get("agent-001")  # "sess-abc"
    """

    def __init__(self) -> None:
        self._sessions: dict[str, str] = {}

    def register(self, agent_id: str, session_id: str) -> None:
        """Store the agent_id to session_id mapping.

        If the agent_id already has a mapping, it is overwritten.

        Args:
            agent_id: Unique identifier for the agent.
            session_id: SDK session ID to associate with the agent.
        """
        self._sessions[agent_id] = session_id

    def get(self, agent_id: str) -> str | None:
        """Return the session_id for the given agent_id, or None if not found.

        Args:
            agent_id: Unique identifier for the agent.

        Returns:
            The stored session_id, or None if no mapping exists.
        """
        return self._sessions.get(agent_id)

    def remove(self, agent_id: str) -> None:
        """Remove the mapping for the given agent_id.

        No-op if the agent_id is not registered.

        Args:
            agent_id: Unique identifier for the agent to remove.
        """
        self._sessions.pop(agent_id, None)

    def save(self, path: Path) -> None:
        """Atomically write the registry to a JSON file.

        Uses filelock + tempfile + os.replace to prevent partial writes.
        The lock file is placed at path.with_suffix('.json.lock').

        Args:
            path: Destination path for the sessions JSON file.
        """
        lock_path = path.with_suffix(".json.lock")
        lock = filelock.FileLock(str(lock_path), timeout=10.0)
        with lock:
            parent = path.parent
            parent.mkdir(parents=True, exist_ok=True)
            data = json.dumps(self._sessions, indent=2)
            fd, tmp_path = tempfile.mkstemp(dir=parent, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(data)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp_path, path)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise

    @classmethod
    def load(cls, path: Path) -> SessionRegistry:
        """Load a SessionRegistry from a JSON file.

        Returns an empty registry if the file does not exist or contains
        invalid JSON — no exception is raised for missing/corrupt files.

        Args:
            path: Path to the sessions JSON file.

        Returns:
            A new SessionRegistry populated from the file, or an empty one.
        """
        registry = cls()
        if not path.exists():
            return registry
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                registry._sessions = {
                    str(k): str(v) for k, v in data.items()
                }
        except (json.JSONDecodeError, ValueError, OSError):
            pass
        return registry
