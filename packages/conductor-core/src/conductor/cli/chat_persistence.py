"""Chat history persistence for crash-safe session storage.

Stores chat sessions as JSON files under `.conductor/chat_sessions/`,
one file per session. Each turn is appended and flushed immediately
so that history survives crashes and process kills (SESS-05).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class ChatHistoryStore:
    """Persist chat turns to disk for crash recovery.

    Storage layout::

        .conductor/chat_sessions/
            <session_id>.json   # one file per session

    Each session file contains::

        {
            "session_id": "...",
            "created_at": "ISO-8601",
            "turns": [
                {"role": "user",      "content": "...", "timestamp": "...", "token_count": 0},
                {"role": "assistant", "content": "...", "timestamp": "...", "token_count": 123},
                ...
            ]
        }
    """

    def __init__(self, base_dir: Path | str) -> None:
        self._base_dir = Path(base_dir) / "chat_sessions"
        self._base_dir.mkdir(parents=True, exist_ok=True)

        self._session_id = uuid.uuid4().hex[:12]
        self._created_at = datetime.now(UTC).isoformat()
        self._turns: list[dict[str, Any]] = []
        self._path = self._base_dir / f"{self._session_id}.json"

        # Write initial empty session file
        self._flush()

    @property
    def session_id(self) -> str:
        return self._session_id

    def save_turn(self, role: str, content: str, token_count: int = 0) -> None:
        """Append a turn and flush to disk immediately."""
        turn = {
            "role": role,
            "content": content,
            "timestamp": datetime.now(UTC).isoformat(),
            "token_count": token_count,
        }
        self._turns.append(turn)
        self._flush()

    def _flush(self) -> None:
        """Write the full session to disk atomically via temp-file rename."""
        data = {
            "session_id": self._session_id,
            "created_at": self._created_at,
            "turns": self._turns,
        }
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    # -- read helpers -------------------------------------------------------

    @classmethod
    def load_sessions(cls, base_dir: Path | str) -> list[dict[str, Any]]:
        """Return metadata for all stored sessions (newest first)."""
        sessions_dir = Path(base_dir) / "chat_sessions"
        if not sessions_dir.exists():
            return []

        sessions: list[dict[str, Any]] = []
        for p in sessions_dir.glob("*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                sessions.append({
                    "session_id": data["session_id"],
                    "created_at": data["created_at"],
                    "turn_count": len(data.get("turns", [])),
                })
            except (json.JSONDecodeError, KeyError):
                continue

        sessions.sort(key=lambda s: s["created_at"], reverse=True)
        return sessions

    @classmethod
    def load_session(cls, base_dir: Path | str, session_id: str) -> dict[str, Any] | None:
        """Load a full session by ID. Returns None if not found."""
        path = Path(base_dir) / "chat_sessions" / f"{session_id}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, KeyError):
            return None
