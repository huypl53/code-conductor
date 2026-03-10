"""Tests for SessionRegistry — agent-to-session mapping with persistent storage.

All file operations use pytest's tmp_path fixture. No real SDK interactions.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conductor.orchestrator.session_registry import SessionRegistry


# ---------------------------------------------------------------------------
# TestSessionRegistry01CRUD
# ---------------------------------------------------------------------------


class TestSessionRegistry01CRUD:
    """Basic register/get/remove operations."""

    def test_register_and_get_returns_session_id(self):
        """register(agent_id, session_id) stores the mapping; get() retrieves it."""
        registry = SessionRegistry()
        registry.register("agent-001", "sess-abc")
        assert registry.get("agent-001") == "sess-abc"

    def test_get_unknown_agent_returns_none(self):
        """get() returns None for agent_id that was never registered."""
        registry = SessionRegistry()
        assert registry.get("unknown-agent") is None

    def test_remove_deletes_mapping(self):
        """remove() deletes the agent-to-session mapping."""
        registry = SessionRegistry()
        registry.register("agent-001", "sess-abc")
        registry.remove("agent-001")
        assert registry.get("agent-001") is None

    def test_remove_unknown_agent_no_error(self):
        """remove() on an unknown agent_id does not raise."""
        registry = SessionRegistry()
        registry.remove("never-existed")  # should not raise

    def test_register_overwrites_existing_mapping(self):
        """Registering the same agent_id twice overwrites the previous session_id."""
        registry = SessionRegistry()
        registry.register("agent-001", "sess-old")
        registry.register("agent-001", "sess-new")
        assert registry.get("agent-001") == "sess-new"

    def test_multiple_agents_tracked_independently(self):
        """Multiple agents can be registered without interfering."""
        registry = SessionRegistry()
        registry.register("agent-001", "sess-aaa")
        registry.register("agent-002", "sess-bbb")
        assert registry.get("agent-001") == "sess-aaa"
        assert registry.get("agent-002") == "sess-bbb"


# ---------------------------------------------------------------------------
# TestSessionRegistry02Persistence
# ---------------------------------------------------------------------------


class TestSessionRegistry02Persistence:
    """Save and load from JSON file."""

    def test_save_writes_json_file(self, tmp_path: Path):
        """save(path) creates a JSON file at the given path."""
        registry = SessionRegistry()
        registry.register("agent-001", "sess-abc")
        file_path = tmp_path / "sessions.json"
        registry.save(file_path)
        assert file_path.exists()

    def test_save_writes_valid_json(self, tmp_path: Path):
        """save(path) writes valid JSON containing the agent-to-session mapping."""
        registry = SessionRegistry()
        registry.register("agent-001", "sess-abc")
        file_path = tmp_path / "sessions.json"
        registry.save(file_path)
        data = json.loads(file_path.read_text())
        assert data == {"agent-001": "sess-abc"}

    def test_load_reads_registry_back(self, tmp_path: Path):
        """load(path) reads a saved registry and returns correct mappings."""
        file_path = tmp_path / "sessions.json"
        file_path.write_text(json.dumps({"agent-001": "sess-abc"}))
        registry = SessionRegistry.load(file_path)
        assert registry.get("agent-001") == "sess-abc"

    def test_load_nonexistent_path_returns_empty_registry(self, tmp_path: Path):
        """load() returns an empty registry when the file does not exist — no crash."""
        file_path = tmp_path / "does-not-exist.json"
        registry = SessionRegistry.load(file_path)
        assert registry.get("agent-001") is None

    def test_load_invalid_json_returns_empty_registry(self, tmp_path: Path):
        """load() returns an empty registry when the file contains invalid JSON."""
        file_path = tmp_path / "sessions.json"
        file_path.write_text("this is not json {{{")
        registry = SessionRegistry.load(file_path)
        assert registry.get("agent-001") is None

    def test_round_trip_register_save_load_get(self, tmp_path: Path):
        """Full round-trip: register, save, load into new instance, get returns same value."""
        file_path = tmp_path / "sessions.json"

        # Original registry — register and save
        original = SessionRegistry()
        original.register("agent-001", "sess-abc")
        original.register("agent-002", "sess-def")
        original.save(file_path)

        # New registry loaded from file
        loaded = SessionRegistry.load(file_path)
        assert loaded.get("agent-001") == "sess-abc"
        assert loaded.get("agent-002") == "sess-def"

    def test_save_overwrites_existing_file(self, tmp_path: Path):
        """save() replaces the existing file contents atomically."""
        file_path = tmp_path / "sessions.json"

        registry_v1 = SessionRegistry()
        registry_v1.register("agent-001", "sess-old")
        registry_v1.save(file_path)

        registry_v2 = SessionRegistry()
        registry_v2.register("agent-001", "sess-new")
        registry_v2.save(file_path)

        loaded = SessionRegistry.load(file_path)
        assert loaded.get("agent-001") == "sess-new"
